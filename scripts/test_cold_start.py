import os
import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COX_MODEL_PATH = os.path.join(PROJECT_ROOT, "ml_package", "cox_model.joblib")
COX_COLS_PATH = os.path.join(PROJECT_ROOT, "ml_package", "cox_feature_columns.joblib")

cox_model = joblib.load(COX_MODEL_PATH)
cox_cols = joblib.load(COX_COLS_PATH)

print("Inspecting Cox Model Artifact type:", type(cox_model))

# Build a test row with valid core data but missing milestone and delay metrics
test_cox_data = {
    "project_age": 2.0,
    "original_duration_months": 24.0,
    "original_cost_crore": 100.0,
    "current_cost": 100.0,
    "cumulative_expenditure_crore": 5.0,
    "milestone_completion_percentage": np.nan,  # Cold-start case
    "anticipated_delay_from_original": np.nan,  # Cold-start case
    "remaining_org_months": 22.0,
    "sector_overrun_rate": 0.15,
    "agency_overrun_rate": 0.18
}

test_df = pd.DataFrame([test_cox_data])[cox_cols]

try:
    if hasattr(cox_model, "predict_partial_hazard"):
        hazard = cox_model.predict_partial_hazard(test_df)
    elif hasattr(cox_model, "predict"):
        hazard = cox_model.predict(test_df)
    print(f"[SUCCESS] Cox model processed NaNs natively. Hazard output: {hazard}")
except Exception as e:
    print(f"[ALERT] Cox model cannot handle NaNs natively: {e}")
    print("Action Required: Check predictor.py or apply fallback imputation.")