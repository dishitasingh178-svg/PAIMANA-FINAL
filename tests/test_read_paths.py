"""Read-path optimisations: the PostgreSQL query paths must return exactly what
the portable (SQLite) paths return, and cached reads must follow writes."""
import os
from datetime import date, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from api.models.models import Alert, Prediction, Project, ProjectUpdate
from api.routers import analytics, dashboard
from api.services import read_cache
from api.services.alert_priority import actionable_alerts


def seed(db):
    """Edge cases: no updates, no predictions, tied generated_at, NULL money/dates."""
    db.add_all([
        Project(project_id="a", project_name="A", sector="RAILWAYS", state="Delhi", original_cost_crore=100, original_commissioning_date=date(2024, 1, 1)),
        Project(project_id="b", project_name="B", sector="ROADS", state="Goa", original_cost_crore=250, original_commissioning_date=date(2025, 6, 1)),
        Project(project_id="c", project_name="C", sector="RAILWAYS", state=None, original_cost_crore=None, original_commissioning_date=None),
        Project(project_id="d", project_name="D", sector=None, state="Delhi", original_cost_crore=40, original_commissioning_date=date(2023, 3, 1)),
    ])
    db.flush()
    updates = [
        ("a", "2024-01", 120, 50, date(2024, 6, 1), None),
        ("a", "2024-03", 150, 90, None, date(2025, 2, 1)),
        ("a", "2024-02", 130, 70, date(2024, 9, 1), None),
        ("b", "2024-05", None, 20, None, None),
        ("c", "2024-04", 60, None, date(2026, 1, 1), date(2026, 5, 1)),
    ]
    for i, (pid, month, revised, spent, rdate, adate) in enumerate(updates, start=1):
        db.add(ProjectUpdate(id=i, project_id=pid, report_month=month, revised_cost_crore=revised, cumulative_expenditure_crore=spent, revised_commissioning_date=rdate, anticipated_commissioning_date=adate))
    predictions = [
        (1, "a", 40, "MODERATE", datetime(2024, 3, 1)),
        (2, "a", 72, "HIGH", datetime(2024, 4, 1)),
        (3, "b", 55, "HIGH", datetime(2024, 5, 1)),
        (4, "b", 30, "LOW", datetime(2024, 5, 1)),       # same timestamp: highest id wins
        (5, "d", 91, "CRITICAL", datetime(2024, 1, 1)),
    ]
    for pid_, pid, score, tier, at in predictions:
        db.add(Prediction(prediction_id=pid_, project_id=pid, report_month="2024-05", cost_risk_probability=.5, schedule_risk_probability=.5, cox_risk=.5, cox_risk_probability=.5, composite_risk_score=score, risk_tier=tier, generated_at=at))
    db.commit()


def responses(db):
    app = FastAPI()
    app.include_router(dashboard.router)
    app.include_router(analytics.router)
    app.dependency_overrides[get_db] = lambda: db
    paths = [f"/api/v1/dashboard/{p}" for p in ("summary", "ongoing-high-risk", "risk-distribution", "alerts", "sector-breakdown")]
    paths += [f"/api/v1/analytics/{p}" for p in ("sectors", "states", "trends", "state-summary")]
    with TestClient(app) as client:
        return {path: (lambda r: (r.status_code, r.json()))(client.get(path)) for path in paths}


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="Set TEST_POSTGRES_URL to compare PostgreSQL and portable read paths")
def test_postgres_read_paths_match_portable_paths():
    sqlite = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(sqlite)
    url = os.environ["TEST_POSTGRES_URL"]
    admin = create_engine(url)
    schema = "read_paths_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    pg = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(pg)
        with Session(sqlite) as a, Session(pg) as b:
            seed(a)
            seed(b)
            assert dashboard._summary_totals(b) == dashboard._summary_totals_python(b)
            expected, actual = responses(a), responses(b)
            assert all(status == 200 for status, _ in expected.values())
            assert actual == expected
    finally:
        pg.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        sqlite.dispose()


def test_cached_alerts_follow_writes(db):
    read_cache.invalidate()
    seed(db)
    db.add(Alert(project_id="a", alert_type="ML_RISK_WARNING", severity="CRITICAL", message="[2024-03] Model warning"))
    db.commit()
    first = actionable_alerts(db)
    assert actionable_alerts(db) is first                    # unchanged data: reused

    db.add(Alert(project_id="b", alert_type="ML_RISK_WARNING", severity="WATCH", message="[2024-05] Model warning"))
    db.commit()
    second = actionable_alerts(db)
    assert second is not first and len(second) == len(first) + 1

    alert = db.query(Alert).filter_by(project_id="b").one()
    alert.status = "DISMISSED"                                  # in-place edit, no new row
    db.commit()
    third = actionable_alerts(db)
    assert third is not second

    db.add(Alert(project_id="d", alert_type="ML_RISK_WARNING", severity="WATCH", message="[2024-01] Model warning"))
    db.flush()
    db.rollback()                                               # rolled-back write must not survive
    assert actionable_alerts(db) is not third


def test_cache_rejects_other_process_writes(db):
    read_cache.invalidate()
    seed(db)
    calls = []
    compute = lambda: calls.append(1) or len(calls)
    assert read_cache.cached("t", db, compute) == 1
    assert read_cache.cached("t", db, compute) == 1         # first reuse records the fingerprint
    # A write the ORM hooks cannot see (another process): only the fingerprint catches it.
    with db.get_bind().begin() as conn:
        conn.execute(text("INSERT INTO alerts (alert_id, project_id, alert_type, severity, message, status) VALUES (99, 'a', 'X', 'WATCH', 'm', 'NEW')"))
    assert read_cache.cached("t", db, compute) == 2
