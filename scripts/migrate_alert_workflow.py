"""Run with python -m scripts.migrate_alert_workflow using existing DATABASE_URL."""
from pathlib import Path
from sqlalchemy import text


def migrate(engine):
    if engine.dialect.name != "postgresql":
        return  # Isolated SQLite tests use freshly created tables.
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '30s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(72491602)"))
        for statement in sql.split(";"):
            if statement.strip():
                connection.execute(text(statement))


if __name__ == "__main__":
    from database import engine
    migrate(engine)
    print("Alert workflow migration complete.")
