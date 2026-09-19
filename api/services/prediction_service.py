"""Canonical prediction service used by API and PDF ingestion."""

from datetime import datetime
from typing import Iterable, Tuple

from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session, sessionmaker

from database import engine
from api.models.models import Project, Prediction, Alert
from api.ml.feature_engineering import build_feature_snapshot
import ml_package.predictor as predictor


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def generate_prediction(db: Session, project_id: str, report_month: str) -> Prediction:
    clean_project_id = str(project_id).strip()
    target_month = str(report_month).strip()[:7]

    project = (
        db.query(Project)
        .filter(func.trim(cast(Project.project_id, String)) == clean_project_id)
        .first()
    )
    if not project:
        raise ValueError(f"Project '{clean_project_id}' not found in the database")

    features_df = build_feature_snapshot(
        project_id=clean_project_id,
        target_report_month=target_month,
        db=db,
    )
    prediction_result = predictor.predict_project_row(features_df)

    prediction = (
        db.query(Prediction)
        .filter(
            func.trim(cast(Prediction.project_id, String)) == clean_project_id,
            Prediction.report_month == target_month,
        )
        .order_by(Prediction.prediction_id.desc())
        .first()
    )

    if prediction is None:
        prediction = Prediction(
            project_id=str(project.project_id).strip(),
            report_month=target_month,
            **prediction_result,
        )
        db.add(prediction)
    else:
        for key, value in prediction_result.items():
            setattr(prediction, key, value)
        prediction.model_version = prediction.model_version or "1.0.0"
        prediction.generated_at = datetime.utcnow()

    db.flush()

    if prediction.risk_tier in {"ELEVATED", "CRITICAL"}:
        alert = (
            db.query(Alert)
            .filter(
                Alert.project_id == str(project.project_id).strip(),
                Alert.alert_type == "ML_RISK_WARNING",
                Alert.is_resolved.is_(False),
            )
            .order_by(Alert.triggered_at.desc(), Alert.alert_id.desc())
            .first()
        )

        message = (
            f"Project reached {prediction.risk_tier} status "
            f"(Score: {float(prediction.composite_risk_score or 0.0):.1f}/100)."
        )

        if alert is None:
            db.add(Alert(
                project_id=str(project.project_id).strip(),
                alert_type="ML_RISK_WARNING",
                severity=prediction.risk_tier,
                message=message,
            ))
        else:
            alert.severity = prediction.risk_tier
            alert.message = message
            alert.triggered_at = datetime.utcnow()
    else:
        # If the current prediction is no longer elevated/critical, resolve
        # the existing unresolved ML alert instead of creating another one.
        (
            db.query(Alert)
            .filter(
                Alert.project_id == str(project.project_id).strip(),
                Alert.alert_type == "ML_RISK_WARNING",
                Alert.is_resolved.is_(False),
            )
            .update({"is_resolved": True}, synchronize_session=False)
        )

    db.commit()
    db.refresh(prediction)
    return prediction


def generate_predictions_for_pairs(pairs: Iterable[Tuple[str, str]]) -> None:
    """Run predictions in a separate DB session for a PDF background task."""
    db = SessionLocal()
    try:
        for project_id, report_month in sorted(set(pairs)):
            try:
                generate_prediction(db, project_id, report_month)
            except Exception as exc:
                db.rollback()
                print(
                    f"[PDF PREDICTION WARNING] {project_id}/{report_month}: {exc}",
                    flush=True,
                )
    finally:
        db.close()
