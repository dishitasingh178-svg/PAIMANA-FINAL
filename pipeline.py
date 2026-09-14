import io
from pathlib import Path
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DB_URI = os.getenv("DATABASE_URL")

if not DB_URI:
    raise RuntimeError("DATABASE_URL is not set. Create a .env file in the project root.")

engine = create_engine(DB_URI)

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = os.getenv("PAIMANA_CLEAN_CSV", str(BASE_DIR / "sushi_superClean.csv"))
engine = create_engine(DB_URI)

PROJECT_COLS = [
    "project_id", "project_name", "sector", "implementing_agency", "state",
    "date_of_approval", "original_cost_crore", "original_commissioning_date"
]
UPDATE_COLS = [
    "project_id", "report_month", "serial_no", "revised_cost_crore",
    "anticipated_cost_crore", "cumulative_expenditure_crore",
    "revised_commissioning_date", "anticipated_commissioning_date",
    "delay_original_months", "delay_revised_months", "milestones_achieved", "milestones_total"
]
REQUIRED = PROJECT_COLS + [c for c in UPDATE_COLS if c not in PROJECT_COLS]


def fast_copy(df: pd.DataFrame, table_name: str):
    conn = engine.raw_connection()
    try:
        cursor = conn.cursor()
        buffer = io.StringIO()
        df.to_csv(buffer, index=False, header=False, na_rep="\\N")
        buffer.seek(0)
        cols = f"({', '.join(df.columns)})"
        cursor.copy_expert(f"COPY {table_name} {cols} FROM STDIN WITH (FORMAT CSV, NULL '\\N')", buffer)
        conn.commit()
    finally:
        conn.close()


def run_pipeline():
    path = Path(CSV_FILE)
    if not path.exists():
        raise FileNotFoundError(
            f"Clean 20-column dataset not found: {path}. "
            "PAIMANA expects sushi_superClean.csv here. Do not substitute the 52-column model dataset."
        )

    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Input is not the expected cleaned 20-column stage. Missing columns: {missing}")

    # Preserve the cleaning-stage contract. Extra columns are rejected rather than silently fed into the DB.
    if len(df.columns) != 20:
        raise ValueError(f"Expected exactly 20 cleaned columns, found {len(df.columns)}. Refusing ambiguous import.")

    df = df.copy()
    df["project_id"] = df["project_id"].astype(str).str.strip()
    df["report_month"] = df["report_month"].astype(str).str.slice(0, 7)
    for col in ["date_of_approval", "original_commissioning_date", "revised_commissioning_date", "anticipated_commissioning_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    df = df.sort_values(["project_id", "report_month"])
    projects = df[PROJECT_COLS].drop_duplicates("project_id", keep="last")
    updates = df[UPDATE_COLS].drop_duplicates(["project_id", "report_month"])

    with engine.begin() as conn:
        conn.execute(text((BASE_DIR / "schema.sql").read_text(encoding="utf-8")))

    # Initial local setup is expected to be empty. The explicit deletes make re-imports deterministic.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE predictions, alerts, project_updates, projects RESTART IDENTITY CASCADE"))

    print(f"Importing {len(projects):,} projects and {len(updates):,} monthly updates from {path.name}...")
    fast_copy(projects, "projects")
    fast_copy(updates, "project_updates")
    print("Import complete.")


if __name__ == "__main__":
    run_pipeline()
