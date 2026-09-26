"""Optional real PostgreSQL integration; creates and removes its own test schema."""
import os
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from api.models.models import Alert
from api.services.alert_priority import transition_status
from api.services.alert_cases import update_project_case, get_cases
from scripts.migrate_alert_workflow import migrate


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_URL"), reason="Set TEST_POSTGRES_URL for PostgreSQL migration test")
def test_postgres_migration_and_persistence():
    url = os.environ["TEST_POSTGRES_URL"]
    admin = create_engine(url)
    schema = "triage_test_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        # Reconstruct the original schema to exercise real additive migration.
        sql = Path("schema.sql").read_text(encoding="utf-8")
        sql = '\n'.join(line for line in sql.splitlines() if not any(line.strip().startswith(f + ' ') for f in ('status','status_updated_at','acknowledged_at','resolved_at','dismissed_at','review_note','evidence_updated_at')))
        with engine.begin() as conn:
            for statement in sql.split(';'):
                if statement.strip():
                    conn.execute(text(statement))
            conn.execute(text("INSERT INTO projects (project_id,project_name) VALUES ('legacy','Legacy migration test')"))
            conn.execute(text("INSERT INTO alerts (project_id,alert_type,severity,message,is_resolved) VALUES ('legacy','ML_RISK_WARNING','WATCH','Open',FALSE), ('legacy','SCHEDULE_SLIPPAGE','WATCH','Closed',TRUE)"))
        migrate(engine)
        migrate(engine)
        with Session(engine) as db:
            alerts = db.query(Alert).order_by(Alert.alert_id).all()
            assert [a.status for a in alerts] == ['NEW','RESOLVED']
            aid = alerts[0].alert_id
            for status in ('ACKNOWLEDGED','UNDER_REVIEW','RESOLVED','DISMISSED'):
                transition_status(alerts[0],status,'Persisted note')
                db.commit()
                db.expire_all()
                assert db.get(Alert,aid).status == status
                assert db.get(Alert,aid).is_resolved == (status == 'RESOLVED')
        migrate(engine)
        with Session(engine) as db:
            assert db.get(Alert,aid).status == 'DISMISSED'
            assert db.get(Alert,aid).review_note == 'Persisted note'
        for status in ('NEW', 'ACKNOWLEDGED', 'UNDER_REVIEW', 'RESOLVED', 'DISMISSED'):
            with Session(engine) as db:
                update_project_case(db, 'legacy', status, 'Case note: ' + status)
            engine.dispose()
            with Session(engine) as db:
                case = get_cases(db)[0]
                assert case['workflow_status'] == status
                assert case['review_note'] == 'Case note: ' + status
                assert all(a.status == status for a in db.query(Alert).all())
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
