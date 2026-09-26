"""Canonical prediction service used by API and PDF ingestion."""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session, sessionmaker

from database import engine
from api.models.models import Project, Prediction
from api.ml.feature_engineering import build_feature_snapshot
from api.services.alert_engine import generate_alerts
import ml_package.predictor as predictor


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def generate_prediction(
    db: Session,
    project_id: str,
    report_month: str,
) -> Prediction:

    prediction, _alerts = generate_prediction_with_alerts(
        db,
        project_id,
        report_month,
    )

    return prediction


def generate_prediction_with_alerts(
    db: Session,
    project_id: str,
    report_month: str,
) -> Tuple[Prediction, list]:

    clean_project_id = str(project_id).strip()
    target_month = str(report_month).strip()[:7]

    project = (
        db.query(Project)
        .filter(
            func.trim(
                cast(Project.project_id, String)
            ) == clean_project_id
        )
        .first()
    )

    if not project:
        raise ValueError(
            f"Project '{clean_project_id}' not found in the database"
        )

    # --------------------------------------------------------
    # Build point-in-time ML features
    # --------------------------------------------------------

    features_df = build_feature_snapshot(
        project_id=clean_project_id,
        target_report_month=target_month,
        db=db,
    )

    prediction_result = predictor.predict_project_row(
        features_df
    )

    # --------------------------------------------------------
    # Create or update prediction
    # --------------------------------------------------------

    prediction = (
        db.query(Prediction)
        .filter(
            func.trim(
                cast(Prediction.project_id, String)
            ) == clean_project_id,
            Prediction.report_month == target_month,
        )
        .order_by(
            Prediction.prediction_id.desc()
        )
        .first()
    )

    if prediction is None:

        prediction = Prediction(
            project_id=str(
                project.project_id
            ).strip(),
            report_month=target_month,
            **prediction_result,
        )

        db.add(prediction)

    else:

        for key, value in prediction_result.items():
            setattr(
                prediction,
                key,
                value,
            )

        prediction.model_version = (
            prediction.model_version
            or "1.0.0"
        )

        prediction.generated_at = (
            datetime.utcnow()
        )

    # Make the prediction visible to the alert engine
    # before it queries previous predictions.
    db.flush()

    # --------------------------------------------------------
    # EARLY WARNING ENGINE
    #
    # This is now the ONLY place where prediction-triggered
    # alerts are generated.
    # --------------------------------------------------------

    alerts = generate_alerts(
        db=db,
        project=project,
        target_month=target_month,
        prediction_result=prediction_result,
    ) or []

    # --------------------------------------------------------
    # Commit prediction + alerts together
    # --------------------------------------------------------

    db.commit()
    db.refresh(prediction)

    return prediction, alerts


def generate_predictions_for_pairs(
    pairs: Iterable[Tuple[str, str]],
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """
    Run predictions in a separate DB session for a PDF
    background task.

    Early Warning alerts are generated automatically through
    generate_prediction(). progress_callback, if given, receives
    the running summary after every pair.
    """

    ordered_pairs = sorted(set(pairs))

    summary: Dict[str, Any] = {
        "total": len(ordered_pairs),
        "done": 0,
        "succeeded": 0,
        "failed": 0,
        "alerts_created": 0,
        "alerts_by_severity": {},
        "last_project_id": None,
        "last_error": None,
    }

    db = SessionLocal()

    try:

        for project_id, report_month in ordered_pairs:

            summary["last_project_id"] = project_id
            summary["last_error"] = None

            try:

                _prediction, alerts = generate_prediction_with_alerts(
                    db,
                    project_id,
                    report_month,
                )

                summary["succeeded"] += 1
                summary["alerts_created"] += len(alerts)

                for alert in alerts:
                    severity = str(
                        getattr(alert, "severity", None) or "UNKNOWN"
                    )
                    summary["alerts_by_severity"][severity] = (
                        summary["alerts_by_severity"].get(severity, 0) + 1
                    )

            except Exception as exc:

                db.rollback()

                summary["failed"] += 1
                summary["last_error"] = str(exc)

                print(
                    f"[PDF PREDICTION WARNING] "
                    f"{project_id}/{report_month}: {exc}",
                    flush=True,
                )

            summary["done"] += 1

            if progress_callback:
                progress_callback(summary)

    finally:

        db.close()

    return summary
