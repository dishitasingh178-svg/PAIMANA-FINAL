from datetime import date, timedelta

from api.models.models import Prediction, Project, ProjectUpdate
from api.routers.analytics import get_state_summary


def _prediction(pid, score, month="2024-01"):
    return Prediction(project_id=pid, report_month=month, cost_risk_probability=0.5,
                      schedule_risk_probability=0.5, cox_risk=1, cox_risk_probability=0.5,
                      composite_risk_score=score, risk_tier="X")


def test_state_summary_counts_costs_and_ongoing(db):
    future, past = date.today() + timedelta(days=90), date.today() - timedelta(days=90)
    db.add_all([
        Project(project_id="a", project_name="A", state="Maharashtra", original_cost_crore=100),
        Project(project_id="b", project_name="B", state="MAHARASHTRA ", original_cost_crore=50),
        Project(project_id="c", project_name="C", state=None, original_cost_crore=10),
        Project(project_id="d", project_name="D", state="Kerala", original_cost_crore=5),
    ])
    db.flush()
    db.add_all([
        # older update must be ignored in favour of the latest report month
        ProjectUpdate(project_id="a", report_month="2023-01", anticipated_cost_crore=999, anticipated_commissioning_date=past),
        ProjectUpdate(project_id="a", report_month="2024-01", anticipated_cost_crore=120, anticipated_commissioning_date=future),
        ProjectUpdate(project_id="b", report_month="2024-01", revised_cost_crore=60, revised_commissioning_date=past),
    ])
    db.add_all([_prediction("a", 80), _prediction("b", 55), _prediction("c", 10)])
    db.commit()

    body = get_state_summary(db=db)
    rows = {r["state"]: r for r in body["data"]}
    assert set(rows) == {"MAHARASHTRA", "KERALA", None}
    mh = rows["MAHARASHTRA"]
    assert (mh["projects"], mh["ongoing"]) == (2, 1)             # b's commissioning date has passed
    assert mh["original_cost_crore"] == 150
    assert mh["latest_cost_crore"] == 180                        # 120 (a, latest anticipated) + 60 (b, revised)
    assert mh["ongoing_latest_cost_crore"] == 120
    assert (mh["high_risk"], mh["critical"], mh["ongoing_high_risk"]) == (2, 1, 1)
    # no update -> ongoing (date not reported), cost falls back to the original sanction
    assert rows["KERALA"]["ongoing"] == 1 and rows["KERALA"]["latest_cost_crore"] == 5
    assert rows["KERALA"]["unscored"] == 1
    # blank state is kept separate, never reassigned
    assert rows[None]["projects"] == 1
    assert body["data"][-1]["state"] is None
    assert "commissioning" in body["ongoing_definition"]


def _client(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import get_db
    from api.routers.analytics import router
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _seed_exposure(db):
    future, past = date.today() + timedelta(days=30), date.today() - timedelta(days=30)
    db.add_all([
        Project(project_id="x1", project_name="X1", state="Odisha", original_cost_crore=500),
        Project(project_id="x2", project_name="X2", state="ODISHA", original_cost_crore=300),
        Project(project_id="x3", project_name="X3", state="Odisha", original_cost_crore=200),
        Project(project_id="x4", project_name="X4", state="Odisha", original_cost_crore=999),
        Project(project_id="y1", project_name="Y1", state="  ", original_cost_crore=40),
    ])
    db.flush()
    db.add_all([
        ProjectUpdate(project_id="x1", report_month="2024-05", anticipated_cost_crore=1000, anticipated_commissioning_date=future),
        ProjectUpdate(project_id="x2", report_month="2024-05", revised_cost_crore=400, revised_commissioning_date=future),
        # x3 has no update at all -> ongoing (no date reported), cost falls back to 200
        ProjectUpdate(project_id="x4", report_month="2024-05", anticipated_cost_crore=5000, anticipated_commissioning_date=past),
    ])
    db.add_all([_prediction("x1", 75), _prediction("x2", 20), _prediction("x4", 90), _prediction("y1", 50)])
    # x3 has no prediction (unscored, but ongoing)
    db.commit()


def test_risk_exposure_is_ongoing_cost_weighted_by_score(db):
    _seed_exposure(db)
    rows = {r["state"]: r for r in get_state_summary(db=db)["data"]}
    od = rows["ODISHA"]
    # x1: 1000 * 0.75 = 750 ; x2: 400 * 0.20 = 80 ; x3 ongoing but unscored -> 0 ; x4 not ongoing -> excluded
    assert od["risk_exposure_crore"] == 830.0
    assert od["ongoing"] == 3 and od["ongoing_unscored"] == 1
    assert od["ongoing_latest_cost_crore"] == 1600.0          # 1000 + 400 + 200 (x3 original)
    assert od["ongoing_high_risk"] == 1 and od["high_risk"] == 2   # x1 ongoing>=50 ; x4 also >=50 but not ongoing
    assert od["unscored"] == 1
    # whitespace-only state is "not available", never folded into a real state
    assert rows[None]["projects"] == 1 and rows[None]["risk_exposure_crore"] == 20.0   # 40 * 0.5, no update -> ongoing
    # exposure can never exceed the ongoing cost it is weighted from
    for r in rows.values():
        assert 0 <= r["risk_exposure_crore"] <= r["ongoing_latest_cost_crore"]


def test_state_summary_endpoint_contract(db):
    _seed_exposure(db)
    res = _client(db).get("/api/v1/analytics/state-summary")
    assert res.status_code == 200
    body = res.json()
    assert {"as_of", "ongoing_definition", "risk_exposure_definition", "prediction_basis", "data"} <= set(body)
    assert body["as_of"] == date.today().isoformat()
    expected = {"state", "projects", "ongoing", "original_cost_crore", "latest_cost_crore", "ongoing_latest_cost_crore",
                "high_risk", "critical", "ongoing_high_risk", "unscored", "risk_exposure_crore", "ongoing_unscored"}
    assert body["data"] and all(set(r) == expected for r in body["data"])
    # every number is derived from the rows inserted above (no hardcoded states)
    assert sum(r["projects"] for r in body["data"]) == 5
    assert {r["state"] for r in body["data"]} == {"ODISHA", None}


def test_state_summary_agrees_with_existing_state_analytics(db):
    _seed_exposure(db)
    client = _client(db)
    summary = {r["state"]: r for r in client.get("/api/v1/analytics/state-summary").json()["data"]}
    states = client.get("/api/v1/analytics/states").json()["data"]
    odisha = [r for r in states if (r["state"] or "").strip().upper() == "ODISHA"]
    # /analytics/states groups raw spellings and only counts projects that have a prediction;
    # state-summary counts every project and reports the unscored ones separately.
    assert sum(r["projects"] for r in odisha) == summary["ODISHA"]["projects"] - summary["ODISHA"]["unscored"]
    assert sum(r["high_risk"] for r in odisha) == summary["ODISHA"]["high_risk"]
