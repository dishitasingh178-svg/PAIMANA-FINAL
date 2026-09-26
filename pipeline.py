"""
PAIMANA incremental CSV import pipeline.

Behavior:
- Reads the cleaned PAIMANA CSV.
- Validates the expected 19-column schema.
- Updates existing projects by project_id.
- Inserts new projects.
- Updates existing project_updates by (project_id, report_month).
- Inserts new project_updates.
- Does NOT delete/truncate any rows.
- Does NOT modify predictions or alerts.
- Supports --dry-run.
"""

import argparse
import io
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv()

DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a .env file in the project root."
    )

engine = create_engine(DB_URI)

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = os.getenv(
    "PAIMANA_CLEAN_CSV",
    str(BASE_DIR / "sushi_superClean.csv"),
)

PROJECT_COLS = [
    "project_id",
    "project_name",
    "sector",
    "implementing_agency",
    "state",
    "date_of_approval",
    "original_cost_crore",
    "original_commissioning_date",
]

UPDATE_COLS = [
    "project_id",
    "report_month",
    "serial_no",
    "revised_cost_crore",
    "anticipated_cost_crore",
    "cumulative_expenditure_crore",
    "revised_commissioning_date",
    "anticipated_commissioning_date",
    "delay_original_months",
    "delay_revised_months",
    "milestones_achieved",
    "milestones_total",
]

REQUIRED = PROJECT_COLS + [
    c for c in UPDATE_COLS if c not in PROJECT_COLS
]

DATE_COLS = [
    "date_of_approval",
    "original_commissioning_date",
    "revised_commissioning_date",
    "anticipated_commissioning_date",
]

INTEGER_COLS = [
    "serial_no",
    "milestones_achieved",
    "milestones_total",
]


def normalize_integer_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    PostgreSQL INTEGER columns cannot receive values such as '1.0'.
    pandas can read integer columns as floats when they contain NULLs,
    so normalize them to pandas nullable Int64 before COPY.

    Non-integer numeric values are rejected rather than silently rounded.
    """
    df = df.copy()

    for col in INTEGER_COLS:
        numeric = pd.to_numeric(df[col], errors="coerce")

        non_null = numeric.notna()
        fractional = numeric[non_null] % 1 != 0

        if fractional.any():
            bad_values = numeric[non_null][fractional].head(5).tolist()
            raise ValueError(
                f"Column '{col}' contains non-integer values: {bad_values}. "
                "The database column is INTEGER, so the CSV must contain whole numbers."
            )

        df[col] = numeric.astype("Int64")

    return df


def load_and_validate_csv(path: Path):
    """Load and normalize the cleaned PAIMANA CSV."""
    if not path.exists():
        raise FileNotFoundError(f"CSV dataset not found: {path}")

    df = pd.read_csv(path)

    # Ignore pandas-generated index columns from CSV exports.
    df = df.loc[:, ~df.columns.astype(str).str.match(r"^Unnamed:")]

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Input is missing required columns: {missing}")

    if len(df.columns) != 19:
        raise ValueError(
            f"Expected exactly 19 cleaned columns, found {len(df.columns)}. "
            "Refusing ambiguous import."
        )

    extra = [c for c in df.columns if c not in REQUIRED]
    if extra:
        raise ValueError(f"Unexpected columns found: {extra}")

    df = df.copy()

    df["project_id"] = df["project_id"].astype(str).str.strip()
    if df["project_id"].eq("").any():
        raise ValueError("CSV contains an empty project_id.")

    # Convert report_month to the database's VARCHAR(7) YYYY-MM format.
    # Invalid values are rejected rather than silently becoming bad keys.
    report_month_raw = df["report_month"].astype(str).str.strip()
    report_month_parsed = pd.to_datetime(
        report_month_raw,
        errors="coerce",
        format="mixed",
    )

    invalid_report_month = report_month_parsed.isna()
    if invalid_report_month.any():
        examples = report_month_raw[invalid_report_month].head(5).tolist()
        raise ValueError(
            f"CSV contains invalid report_month values: {examples}"
        )

    df["report_month"] = report_month_parsed.dt.strftime("%Y-%m")

    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    df = normalize_integer_columns(df)

    # Preserve the original pipeline's project selection behavior:
    # after sorting by month, the latest row supplies project-level fields.
    df = df.sort_values(["project_id", "report_month"])

    projects = (
        df[PROJECT_COLS]
        .drop_duplicates("project_id", keep="last")
        .copy()
    )

    # The database has UNIQUE(project_id, report_month).
    updates = (
        df[UPDATE_COLS]
        .drop_duplicates(["project_id", "report_month"])
        .copy()
    )

    return projects, updates


def copy_to_temp_table(
    conn,
    df: pd.DataFrame,
    table_name: str,
    temp_table_name: str,
    columns: list[str],
):
    """
    Copy a DataFrame into a PostgreSQL temporary table.

    The temporary table exists only inside the current transaction.
    It is never a permanent database table.
    """
    conn.execute(
        text(
            f"""
            CREATE TEMP TABLE {temp_table_name}
            (LIKE {table_name} INCLUDING DEFAULTS)
            ON COMMIT DROP
            """
        )
    )

    buffer = io.StringIO()
    df[columns].to_csv(
        buffer,
        index=False,
        header=False,
        na_rep="\\N",
    )
    buffer.seek(0)

    raw_connection = conn.connection
    cursor = raw_connection.cursor()

    try:
        column_sql = ", ".join(columns)
        with cursor.copy(
            f"COPY {temp_table_name} ({column_sql}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')"
        ) as copy:
            copy.write(buffer.getvalue())
    finally:
        cursor.close()


def get_current_counts(conn):
    """Return row counts for all four main tables."""
    result = conn.execute(
        text(
            """
            SELECT
                (SELECT COUNT(*) FROM projects) AS projects,
                (SELECT COUNT(*) FROM project_updates) AS project_updates,
                (SELECT COUNT(*) FROM predictions) AS predictions,
                (SELECT COUNT(*) FROM alerts) AS alerts
            """
        )
    ).mappings().one()

    return {
        "projects": int(result["projects"]),
        "project_updates": int(result["project_updates"]),
        "predictions": int(result["predictions"]),
        "alerts": int(result["alerts"]),
    }


def get_change_counts(conn):
    """Calculate how many rows will be inserted or updated."""
    project_counts = conn.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE p.project_id IS NULL) AS to_insert,
                COUNT(*) FILTER (WHERE p.project_id IS NOT NULL) AS to_update
            FROM tmp_projects_import t
            LEFT JOIN projects p
                ON p.project_id = t.project_id
            """
        )
    ).mappings().one()

    update_counts = conn.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE p.project_id IS NULL) AS to_insert,
                COUNT(*) FILTER (WHERE p.project_id IS NOT NULL) AS to_update
            FROM tmp_project_updates_import t
            LEFT JOIN project_updates p
                ON p.project_id = t.project_id
               AND p.report_month = t.report_month
            """
        )
    ).mappings().one()

    return {
        "projects_to_insert": int(project_counts["to_insert"]),
        "projects_to_update": int(project_counts["to_update"]),
        "updates_to_insert": int(update_counts["to_insert"]),
        "updates_to_update": int(update_counts["to_update"]),
    }


def upsert_from_temp(
    conn,
    table_name: str,
    temp_table_name: str,
    columns: list[str],
    conflict_columns: list[str],
):
    """Insert new rows and update existing rows using PostgreSQL ON CONFLICT."""
    column_sql = ", ".join(columns)
    conflict_sql = ", ".join(conflict_columns)

    update_columns = [
        c for c in columns
        if c not in conflict_columns
    ]

    set_sql = ", ".join(
        f"{column} = EXCLUDED.{column}"
        for column in update_columns
    )

    conn.execute(
        text(
            f"""
            INSERT INTO {table_name} ({column_sql})
            SELECT {column_sql}
            FROM {temp_table_name}
            ON CONFLICT ({conflict_sql})
            DO UPDATE SET
                {set_sql}
            """
        )
    )


def run_pipeline(dry_run: bool = False):
    path = Path(CSV_FILE)

    projects, updates = load_and_validate_csv(path)

    print()
    print("=" * 64)
    print("PAIMANA INCREMENTAL CSV IMPORT")
    print("=" * 64)
    print(f"CSV: {path}")
    print(f"CSV projects: {len(projects):,}")
    print(f"CSV monthly updates: {len(updates):,}")
    print()

    # No schema.sql execution and no TRUNCATE/DELETE.
    # This importer only changes projects and project_updates.
    with engine.begin() as conn:
        required_tables = {
            "projects",
            "project_updates",
            "predictions",
            "alerts",
        }

        existing_tables = set(
            conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                          'projects',
                          'project_updates',
                          'predictions',
                          'alerts'
                      )
                    """
                )
            ).scalars().all()
        )

        missing_tables = required_tables - existing_tables
        if missing_tables:
            raise RuntimeError(
                "Required database tables are missing: "
                + ", ".join(sorted(missing_tables))
            )

        before = get_current_counts(conn)

        print("CURRENT DATABASE COUNTS")
        print(f"  projects:        {before['projects']:,}")
        print(f"  project_updates: {before['project_updates']:,}")
        print(f"  predictions:     {before['predictions']:,}")
        print(f"  alerts:          {before['alerts']:,}")
        print()

        # Temporary tables are used for efficient comparison and bulk loading.
        # They are dropped automatically at transaction end.
        copy_to_temp_table(
            conn,
            projects,
            "projects",
            "tmp_projects_import",
            PROJECT_COLS,
        )

        copy_to_temp_table(
            conn,
            updates,
            "project_updates",
            "tmp_project_updates_import",
            UPDATE_COLS,
        )

        changes = get_change_counts(conn)

        print("IMPORT PLAN")
        print(f"  projects to INSERT:        {changes['projects_to_insert']:,}")
        print(f"  projects to UPDATE:        {changes['projects_to_update']:,}")
        print(f"  updates to INSERT:         {changes['updates_to_insert']:,}")
        print(f"  updates to UPDATE:         {changes['updates_to_update']:,}")
        print("  predictions:               UNCHANGED")
        print("  alerts:                    UNCHANGED")
        print()

        if dry_run:
            print("DRY RUN COMPLETE")
            print(
                "No permanent database rows were changed. "
                "Only temporary tables were used for comparison."
            )
            print("=" * 64)
            return

        print("Writing projects...")
        upsert_from_temp(
            conn,
            "projects",
            "tmp_projects_import",
            PROJECT_COLS,
            ["project_id"],
        )

        print("Writing monthly project updates...")
        upsert_from_temp(
            conn,
            "project_updates",
            "tmp_project_updates_import",
            UPDATE_COLS,
            ["project_id", "report_month"],
        )

        after = get_current_counts(conn)

        # Hard safety checks.
        if after["predictions"] != before["predictions"]:
            raise RuntimeError(
                "SAFETY CHECK FAILED: predictions row count changed. "
                "Rolling back the transaction."
            )

        if after["alerts"] != before["alerts"]:
            raise RuntimeError(
                "SAFETY CHECK FAILED: alerts row count changed. "
                "Rolling back the transaction."
            )

        print()
        print("FINAL DATABASE COUNTS")
        print(f"  projects:        {after['projects']:,}")
        print(f"  project_updates: {after['project_updates']:,}")
        print(f"  predictions:     {after['predictions']:,}")
        print(f"  alerts:          {after['alerts']:,}")
        print()

        print("IMPORT COMPLETE")
        print("Predictions and alerts were not modified.")
        print("=" * 64)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Incrementally import PAIMANA cleaned CSV data."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the import plan without modifying permanent database rows.",
    )
    args = parser.parse_args()

    run_pipeline(dry_run=args.dry_run)
