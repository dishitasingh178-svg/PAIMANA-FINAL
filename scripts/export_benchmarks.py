import os
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(PROJECT_ROOT, "5-star edible sushi.csv")
if not os.path.exists(CSV_PATH):
    CSV_PATH = os.path.join(PROJECT_ROOT, "superReady_sushi.csv")

df = pd.read_csv(CSV_PATH, low_memory=False)

# Extract unique lookup records per agency, sector, and report month
benchmarks = df[[
    "project_id", "report_month", "sector",
    "agency_overrun_rate", "agency_project_count_as_of_T", "sector_overrun_rate"
]].drop_duplicates()

OUTPUT_PATH = os.path.join(PROJECT_ROOT, "ml_package", "benchmark_lookups.parquet")
benchmarks.to_parquet(OUTPUT_PATH, index=False)
print(f"Saved precomputed benchmarks to {OUTPUT_PATH}")