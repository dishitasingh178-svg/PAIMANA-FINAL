
import json
import os

import joblib
import numpy as np
import pandas as pd

# Force paths to resolve inside ml_package/ regardless of where Uvicorn is launched
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

MANIFEST_PATH = os.path.join(PACKAGE_DIR, "model_manifest.json")

# Load model manifest JSON
if os.path.exists(MANIFEST_PATH):
    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)
else:
    manifest = {
        "package_version": "1.0.0",
        "baseline_cumulative_hazard": 0.15
    }

# Alias package_metadata to manifest to resolve NameError
package_metadata = manifest


COST_MODEL_PATH = os.path.join(PACKAGE_DIR, "cost_final_model.joblib")
SCHEDULE_MODEL_PATH = os.path.join(PACKAGE_DIR, "schedule_final_model.joblib")
COX_MODEL_PATH = os.path.join(PACKAGE_DIR, "cox_model.joblib")
FEATURE_COLS_PATH = os.path.join(PACKAGE_DIR, "feature_columns.joblib")
COX_COLS_PATH = os.path.join(PACKAGE_DIR, "cox_feature_columns.joblib")
cost_final_model = joblib.load(COST_MODEL_PATH)
schedule_final_model = joblib.load(SCHEDULE_MODEL_PATH)
cox_model = joblib.load(COX_MODEL_PATH)
feature_columns = joblib.load(FEATURE_COLS_PATH)
cox_feature_columns = joblib.load(COX_COLS_PATH)

with open(MANIFEST_PATH, "r") as f:
    manifest = json.load(f)

def load_artifacts():
    """No-op if artifacts are already loaded on import."""
    pass

# ============================================================
# UNIFIED PREDICTION FUNCTION
# ============================================================

def predict_project_row(project_row):
    """
    Takes one engineered project feature row and returns
    all downstream model outputs.

    Accepted input:
        - dict
        - pandas Series
        - pandas DataFrame
    """

    # --------------------------------------------------------
    # 1. Convert input into one-row DataFrame
    # --------------------------------------------------------

    if isinstance(project_row, pd.Series):
        row = project_row.to_frame().T.copy()

    elif isinstance(project_row, dict):
        row = pd.DataFrame([project_row])

    elif isinstance(project_row, pd.DataFrame):
        row = project_row.copy()

    else:
        raise TypeError(
            "project_row must be a dict, Series, or DataFrame"
        )

    # Make sure exactly one prediction row is being processed.
    if len(row) != 1:
        raise ValueError(
            f"Expected exactly one project row, received {len(row)} rows."
        )

    # --------------------------------------------------------
    # 2. Make sure all 47 XGBoost features exist
    # --------------------------------------------------------

    missing_features = [
        col
        for col in feature_columns
        if col not in row.columns
    ]

    if missing_features:
        raise ValueError(
            f"Missing required features: {missing_features}"
        )

    # Preserve the exact feature order from the trained model.
    xgb_row = row[feature_columns].copy()

    # --------------------------------------------------------
    # 3. Cost risk
    # --------------------------------------------------------

    try:
        cost_probability = float(
            cost_final_model.predict_proba(
                xgb_row
            )[0, 1]
        )
    except Exception as exc:
        raise ValueError(
            f"Cost-risk model inference failed: {exc}"
        )

    # --------------------------------------------------------
    # 4. Schedule risk
    # --------------------------------------------------------

    try:
        schedule_probability = float(
            schedule_final_model.predict_proba(
                xgb_row
            )[0, 1]
        )
    except Exception as exc:
        raise ValueError(
            f"Schedule-risk model inference failed: {exc}"
        )

    # --------------------------------------------------------
    # 5. Cox risk
    # --------------------------------------------------------

    missing_cox_features = [
        col
        for col in cox_feature_columns
        if col not in row.columns
    ]

    if missing_cox_features:
        raise ValueError(
            "Missing required Cox features: "
            f"{missing_cox_features}"
        )

    cox_row = row[cox_feature_columns].copy()

    # Cox cannot accept NaN values.
    #
    # For missing values, use the training normalization means
    # stored by the fitted Cox model.
    for col in cox_feature_columns:

        if cox_row[col].isna().any():

            if hasattr(cox_model, "_norm_mean"):

                norm_mean = cox_model._norm_mean

                if col in norm_mean.index:
                    fill_value = float(
                        norm_mean[col]
                    )
                else:
                    fill_value = 0.0

            else:
                fill_value = 0.0

            cox_row[col] = (
                cox_row[col]
                .fillna(fill_value)
            )

    try:
        cox_risk = float(
            cox_model
            .predict_partial_hazard(cox_row)
            .iloc[0]
        )
    except Exception as exc:
        raise ValueError(
            f"Cox model inference failed: {exc}"
        )

    # --------------------------------------------------------
    # 6. Normalize Cox risk to 0-1
    # --------------------------------------------------------

    cox_risk_probability = float(
        cox_risk / (1.0 + cox_risk)
    )

    # --------------------------------------------------------
    # 7. Composite risk score
    # --------------------------------------------------------

    composite_score = (
        0.40 * cost_probability
        + 0.40 * schedule_probability
        + 0.20 * cox_risk_probability
    ) * 100.0

    composite_score = float(
        np.clip(
            composite_score,
            0.0,
            100.0
        )
    )

    # --------------------------------------------------------
    # 8. Risk tier
    # --------------------------------------------------------

    if composite_score < 25:
        risk_tier = "LOW"

    elif composite_score < 50:
        risk_tier = "WATCH"

    elif composite_score < 75:
        risk_tier = "ELEVATED"

    else:
        risk_tier = "CRITICAL"

    # --------------------------------------------------------
    # 9. Backend-friendly output
    # --------------------------------------------------------

    return {
        "cost_risk_probability": round(
            cost_probability,
            6
        ),

        "schedule_risk_probability": round(
            schedule_probability,
            6
        ),

        "cox_risk": round(
            cox_risk,
            6
        ),

        "cox_risk_probability": round(
            cox_risk_probability,
            6
        ),

        "composite_risk_score": round(
            composite_score,
            4
        ),

        "risk_tier": risk_tier,

        "model_version": (
            package_metadata.get(
                "package_version",
                "1.0.0"
            )
        )
    }

def get_shap_explanation(project_row, top_n=5):
    """
    Return top SHAP contributors for the cost and schedule XGBoost models.
    """

    import shap

    # Convert input to DataFrame
    if isinstance(project_row, pd.Series):
        row = project_row.to_frame().T.copy()
    elif isinstance(project_row, dict):
        row = pd.DataFrame([project_row])
    elif isinstance(project_row, pd.DataFrame):
        row = project_row.copy()
    else:
        raise TypeError(
            "project_row must be a dict, Series, or DataFrame"
        )

    # Make sure all 47 features exist
    missing_features = [
        col for col in feature_columns
        if col not in row.columns
    ]

    if missing_features:
        raise ValueError(
            f"Missing required features: {missing_features}"
        )

    xgb_row = row[feature_columns].copy()

    def explain_model(pipeline, model_name):

        # Get preprocessing and XGBoost model
        preprocessor = pipeline.named_steps["preprocessor"]
        model = pipeline.named_steps["model"]

        # Transform exactly the same way as prediction
        transformed = preprocessor.transform(xgb_row)

        # Get transformed feature names
        feature_names = preprocessor.get_feature_names_out()

        # SHAP explainer
        explainer = shap.TreeExplainer(model)

        shap_values = explainer.shap_values(transformed)

        # Binary XGBoost normally returns one vector
        if isinstance(shap_values, list):
            values = shap_values[1][0]
        else:
            values = shap_values[0]

        results = []

        for name, value in zip(feature_names, values):

            # Remove sklearn transformer prefixes
            clean_name = name.replace("num__", "")
            clean_name = clean_name.replace("cat__", "")

            results.append({
                "feature": clean_name,
                "shap_value": float(value),
                "direction": (
                    "increases_risk"
                    if value > 0
                    else "decreases_risk"
                )
            })

        # Highest absolute SHAP values first
        results.sort(
            key=lambda x: abs(x["shap_value"]),
            reverse=True
        )

        return {
            "model": model_name,
            "drivers": results[:top_n]
        }

    return {
        "cost": explain_model(
            cost_final_model,
            "Cost XGBoost"
        ),
        "schedule": explain_model(
            schedule_final_model,
            "Schedule XGBoost"
        )
    }