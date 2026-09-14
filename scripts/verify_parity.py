import os
import sys
import numpy as np
import pandas as pd

# Add the project root directory to sys.path so modules import properly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from database import SessionLocal
from api.ml.feature_engineering import build_feature_snapshot, FEATURE_COLUMNS

# Path to the reference dataset from model training
REFERENCE_CSV_PATH = os.path.join(PROJECT_ROOT, "5-star edible sushi.csv")
# Fallback alternative if the file uses the other naming convention
if not os.path.exists(REFERENCE_CSV_PATH):
    REFERENCE_CSV_PATH = os.path.join(PROJECT_ROOT, "superReady_sushi.csv")

FLOAT_TOLERANCE = 1e-6


def run_parity_verification(sample_size: int = 10):
    if not os.path.exists(REFERENCE_CSV_PATH):
        print(f"[ERROR] Reference CSV file not found at: {REFERENCE_CSV_PATH}")
        return

    print(f"Loading reference dataset: {REFERENCE_CSV_PATH} ...")
    ref_df = pd.read_csv(REFERENCE_CSV_PATH, low_memory=False)

    # Validate essential identifier columns exist
    if "project_id" not in ref_df.columns or "report_month" not in ref_df.columns:
        print("[ERROR] Reference CSV must contain 'project_id' and 'report_month'.")
        return

    # Filter down to projects with valid report_month
    valid_rows = ref_df.dropna(subset=["project_id", "report_month"]).copy()

    # Pick sample project-month combinations
    sample_df = valid_rows.sample(n=min(sample_size, len(valid_rows)), random_state=42)

    db = SessionLocal()
    total_checks = 0
    passed_checks = 0
    mismatches = []

    print(f"\nStarting Parity Verification across {len(sample_df)} sample rows...\n" + "=" * 70)

    try:
        for idx, row in sample_df.iterrows():
            project_id = str(row["project_id"]).strip()
            report_month = str(row["report_month"]).strip()

            print(f"Testing Project ID: {project_id} | Report Month: {report_month}")

            # 1. Run live reconstruction from PostgreSQL
            try:
                gen_df = build_feature_snapshot(
                    project_id=project_id,
                    target_report_month=report_month,
                    db=db
                )
            except Exception as e:
                print(f"  [FAIL] Failed to build snapshot from database: {e}")
                continue

            # 2. Compare every column in FEATURE_COLUMNS against reference CSV row
            for col in FEATURE_COLUMNS:
                if col not in ref_df.columns:
                    continue

                total_checks += 1
                gen_val = gen_df[col].iloc[0]
                ref_val = row[col]

                # Check 1: Handle NaN / Null Parity
                gen_is_nan = pd.isna(gen_val)
                ref_is_nan = pd.isna(ref_val)

                if gen_is_nan and ref_is_nan:
                    passed_checks += 1
                    continue
                elif gen_is_nan != ref_is_nan:
                    mismatches.append({
                        "project_id": project_id,
                        "report_month": report_month,
                        "feature": col,
                        "generated": gen_val,
                        "reference": ref_val,
                        "reason": "NaN / Presence mismatch"
                    })
                    continue

                # Check 2: String & Categorical Matching
                if isinstance(ref_val, str) or isinstance(gen_val, str):
                    if str(gen_val).strip() == str(ref_val).strip():
                        passed_checks += 1
                    else:
                        mismatches.append({
                            "project_id": project_id,
                            "report_month": report_month,
                            "feature": col,
                            "generated": gen_val,
                            "reference": ref_val,
                            "reason": "Categorical mismatch"
                        })
                    continue

                # Check 3: Boolean Matching
                if isinstance(ref_val, (bool, np.bool_)) or isinstance(gen_val, (bool, np.bool_)):
                    if bool(gen_val) == bool(ref_val):
                        passed_checks += 1
                    else:
                        mismatches.append({
                            "project_id": project_id,
                            "report_month": report_month,
                            "feature": col,
                            "generated": gen_val,
                            "reference": ref_val,
                            "reason": "Boolean mismatch"
                        })
                    continue

                # Check 4: Numeric & Floating Point Comparison (within tolerance)
                try:
                    diff = abs(float(gen_val) - float(ref_val))
                    if diff <= FLOAT_TOLERANCE:
                        passed_checks += 1
                    else:
                        mismatches.append({
                            "project_id": project_id,
                            "report_month": report_month,
                            "feature": col,
                            "generated": gen_val,
                            "reference": ref_val,
                            "diff": diff,
                            "reason": f"Exceeded tolerance ({FLOAT_TOLERANCE})"
                        })
                except (ValueError, TypeError):
                    mismatches.append({
                        "project_id": project_id,
                        "report_month": report_month,
                        "feature": col,
                        "generated": gen_val,
                        "reference": ref_val,
                        "reason": "Type conversion error"
                    })

    finally:
        db.close()

    # 3. Output summary report
    print("\n" + "=" * 70)
    print("PARITY VERIFICATION SUMMARY")
    print(f"Total Feature Checks: {total_checks}")
    print(f"Passed Checks:        {passed_checks}")
    print(f"Failed Checks:        {len(mismatches)}")

    if not mismatches:
        print("\n[SUCCESS] 100% Parity Achieved! Reconstructed features match training data.")
    else:
        print("\n[FAILURE] Discrepancies detected:")
        mismatch_df = pd.DataFrame(mismatches)
        print(mismatch_df.to_string(index=False))


if __name__ == "__main__":
    run_parity_verification(sample_size=10)