import argparse
from pathlib import Path
import pandas as pd

EXPECTED_REQUIRED_COLUMNS = [
    "project_id", "project_name", "sector", "implementing_agency", "state",
    "date_of_approval", "original_cost_crore", "original_commissioning_date",
    "report_month", "serial_no", "revised_cost_crore", "anticipated_cost_crore",
    "cumulative_expenditure_crore", "revised_commissioning_date",
    "anticipated_commissioning_date", "delay_original_months", "delay_revised_months",
    "milestones_achieved", "milestones_total"
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default="sushi_superClean.csv")
    args = parser.parse_args()
    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    df = pd.read_csv(path, nrows=5)
    print(f"columns={len(df.columns)}")
    print("columns:")
    for i, col in enumerate(df.columns, 1): print(f"  {i:02d}. {col}")
    if len(df.columns) != 20:
        raise SystemExit("FAIL: expected the cleaned 20-column database stage, not the 52-column model dataset.")
    missing = [c for c in EXPECTED_REQUIRED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_REQUIRED_COLUMNS]
    if missing:
        raise SystemExit(f"FAIL: missing required cleaned columns: {missing}")
    if extra != ["Unnamed: 0"]:
        raise SystemExit(f"FAIL: expected the cleaned dataset index column Unnamed: 0; extra={extra}")
    print("PASS: cleaned 20-column dataset contract validated. Index column: Unnamed: 0")


if __name__ == "__main__":
    main()
