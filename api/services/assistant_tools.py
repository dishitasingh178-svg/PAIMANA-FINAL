from sqlalchemy.orm import Session

from api.models.models import Project, ProjectUpdate, Prediction, Alert


def search_projects(db: Session, query: str, limit: int = 10):
    """
    Search PAIMANA projects by name, sector, agency, or state.
    Returns structured data for the LLM.
    """

    query = query.strip()

    if not query:
        return []

    search_pattern = f"%{query}%"

    projects = (
        db.query(Project)
        .filter(
            (Project.project_name.ilike(search_pattern))
            | (Project.sector.ilike(search_pattern))
            | (Project.implementing_agency.ilike(search_pattern))
            | (Project.state.ilike(search_pattern))
        )
        .order_by(Project.project_name.asc())
        .limit(limit)
        .all()
    )

    return [
        {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "sector": project.sector,
            "implementing_agency": project.implementing_agency,
            "state": project.state,
            "date_of_approval": (
                project.date_of_approval.isoformat()
                if project.date_of_approval
                else None
            ),
            "original_cost_crore": (
                float(project.original_cost_crore)
                if project.original_cost_crore is not None
                else None
            ),
            "original_commissioning_date": (
                project.original_commissioning_date.isoformat()
                if project.original_commissioning_date
                else None
            ),
        }
        for project in projects
    ]


def get_project(db: Session, project_id: str):
    """
    Get one PAIMANA project by its internal project ID.
    """

    project_id = project_id.strip()

    if not project_id:
        return None

    project = (
        db.query(Project)
        .filter(Project.project_id == project_id)
        .first()
    )

    if not project:
        return None

    return {
        "project_id": project.project_id,
        "project_name": project.project_name,
        "sector": project.sector,
        "implementing_agency": project.implementing_agency,
        "state": project.state,
        "date_of_approval": (
            project.date_of_approval.isoformat()
            if project.date_of_approval
            else None
        ),
        "original_cost_crore": (
            float(project.original_cost_crore)
            if project.original_cost_crore is not None
            else None
        ),
        "original_commissioning_date": (
            project.original_commissioning_date.isoformat()
            if project.original_commissioning_date
            else None
        ),
    }


def get_latest_prediction(db: Session, project_id: str):
    """
    Get the latest prediction for a PAIMANA project.
    """

    project_id = project_id.strip()

    if not project_id:
        return None

    prediction = (
        db.query(Prediction)
        .filter(Prediction.project_id == project_id)
        .order_by(
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .first()
    )

    if not prediction:
        return None

    return {
        "prediction_id": prediction.prediction_id,
        "project_id": prediction.project_id,
        "report_month": prediction.report_month,
        "cost_risk_probability": (
            float(prediction.cost_risk_probability)
            if prediction.cost_risk_probability is not None
            else None
        ),
        "schedule_risk_probability": (
            float(prediction.schedule_risk_probability)
            if prediction.schedule_risk_probability is not None
            else None
        ),
        "cox_risk": (
            float(prediction.cox_risk)
            if prediction.cox_risk is not None
            else None
        ),
        "cox_risk_probability": (
            float(prediction.cox_risk_probability)
            if prediction.cox_risk_probability is not None
            else None
        ),
        "composite_risk_score": (
            float(prediction.composite_risk_score)
            if prediction.composite_risk_score is not None
            else None
        ),
        "risk_tier": prediction.risk_tier,
        "model_version": prediction.model_version,
        "generated_at": (
            prediction.generated_at.isoformat()
            if prediction.generated_at
            else None
        ),
    }


def get_project_updates(
    db: Session,
    project_id: str,
    limit: int = 12,
):
    """
    Get recent monthly updates for a PAIMANA project.
    """

    project_id = project_id.strip()

    if not project_id:
        return []

    updates = (
        db.query(ProjectUpdate)
        .filter(ProjectUpdate.project_id == project_id)
        .order_by(ProjectUpdate.report_month.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "project_id": update.project_id,
            "report_month": update.report_month,
            "serial_no": update.serial_no,
            "revised_cost_crore": (
                float(update.revised_cost_crore)
                if update.revised_cost_crore is not None
                else None
            ),
            "anticipated_cost_crore": (
                float(update.anticipated_cost_crore)
                if update.anticipated_cost_crore is not None
                else None
            ),
            "cumulative_expenditure_crore": (
                float(update.cumulative_expenditure_crore)
                if update.cumulative_expenditure_crore is not None
                else None
            ),
            "revised_commissioning_date": (
                update.revised_commissioning_date.isoformat()
                if update.revised_commissioning_date
                else None
            ),
            "anticipated_commissioning_date": (
                update.anticipated_commissioning_date.isoformat()
                if update.anticipated_commissioning_date
                else None
            ),
            "delay_original_months": (
                float(update.delay_original_months)
                if update.delay_original_months is not None
                else None
            ),
            "delay_revised_months": (
                float(update.delay_revised_months)
                if update.delay_revised_months is not None
                else None
            ),
            "milestones_achieved": update.milestones_achieved,
            "milestones_total": update.milestones_total,
        }
        for update in updates
    ]


def get_project_alerts(
    db: Session,
    project_id: str,
    unresolved_only: bool = False,
    limit: int = 20,
):
    """
    Get alerts for a PAIMANA project.
    """

    project_id = project_id.strip()

    if not project_id:
        return []

    query = (
        db.query(Alert)
        .filter(Alert.project_id == project_id)
    )

    if unresolved_only:
        query = query.filter(Alert.is_resolved == False)

    alerts = (
        query
        .order_by(Alert.triggered_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "alert_id": alert.alert_id,
            "project_id": alert.project_id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "is_resolved": alert.is_resolved,
            "triggered_at": (
                alert.triggered_at.isoformat()
                if alert.triggered_at
                else None
            ),
        }
        for alert in alerts
    ]


def get_risk_history(
    db: Session,
    project_id: str,
    limit: int = 12,
):
    """
    Get historical risk predictions for a PAIMANA project.
    """

    project_id = project_id.strip()

    if not project_id:
        return []

    predictions = (
        db.query(Prediction)
        .filter(Prediction.project_id == project_id)
        .order_by(
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "project_id": prediction.project_id,
            "report_month": prediction.report_month,
            "cost_risk_probability": (
                float(prediction.cost_risk_probability)
                if prediction.cost_risk_probability is not None
                else None
            ),
            "schedule_risk_probability": (
                float(prediction.schedule_risk_probability)
                if prediction.schedule_risk_probability is not None
                else None
            ),
            "cox_risk_probability": (
                float(prediction.cox_risk_probability)
                if prediction.cox_risk_probability is not None
                else None
            ),
            "composite_risk_score": (
                float(prediction.composite_risk_score)
                if prediction.composite_risk_score is not None
                else None
            ),
            "risk_tier": prediction.risk_tier,
            "model_version": prediction.model_version,
            "generated_at": (
                prediction.generated_at.isoformat()
                if prediction.generated_at
                else None
            ),
        }
        for prediction in predictions
    ]


def get_portfolio_risk_summary(
    db: Session,
):
    """
    Get an overall summary of the latest stored PAIMANA predictions.

    Risk tiers are kept consistent with the production ML model:
    LOW, WATCH, ELEVATED, CRITICAL.
    """

    predictions = (
        db.query(Prediction)
        .order_by(
            Prediction.project_id.asc(),
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .all()
    )

    latest_by_project = {}

    for prediction in predictions:
        project_id = str(prediction.project_id).strip()

        if project_id not in latest_by_project:
            latest_by_project[project_id] = prediction

    latest_predictions = list(latest_by_project.values())

    total_projects = len(latest_predictions)

    risk_counts = {
        "critical": 0,
        "elevated": 0,
        "watch": 0,
        "low": 0,
    }

    scores = []

    for prediction in latest_predictions:
        tier = (
            prediction.risk_tier.strip().lower()
            if prediction.risk_tier
            else None
        )

        if tier in risk_counts:
            risk_counts[tier] += 1

        if prediction.composite_risk_score is not None:
            scores.append(float(prediction.composite_risk_score))

    average_risk_score = (
        sum(scores) / len(scores)
        if scores
        else None
    )

    return {
        "total_projects": total_projects,
        "risk_counts": risk_counts,
        "average_composite_risk_score": average_risk_score,
    }

def get_critical_projects(
    db: Session,
    limit: int = 10,
):
    """
    Get projects whose latest prediction is critical risk.
    """

    predictions = (
        db.query(Prediction)
        .join(Project, Prediction.project_id == Project.project_id)
        .order_by(
            Prediction.project_id.asc(),
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .all()
    )

    latest_by_project = {}

    for prediction in predictions:
        if prediction.project_id not in latest_by_project:
            latest_by_project[prediction.project_id] = prediction

    critical_projects = []

    for prediction in latest_by_project.values():

        if (
            prediction.risk_tier
            and prediction.risk_tier.lower() == "critical"
        ):
            project = (
                db.query(Project)
                .filter(Project.project_id == prediction.project_id)
                .first()
            )

            if project:
                critical_projects.append(
                    {
                        "project_id": project.project_id,
                        "project_name": project.project_name,
                        "sector": project.sector,
                        "state": project.state,
                        "implementing_agency": project.implementing_agency,
                        "composite_risk_score": (
                            float(prediction.composite_risk_score)
                            if prediction.composite_risk_score is not None
                            else None
                        ),
                        "risk_tier": prediction.risk_tier,
                        "report_month": prediction.report_month,
                    }
                )

    critical_projects.sort(
        key=lambda x: (
            x["composite_risk_score"]
            if x["composite_risk_score"] is not None
            else -1
        ),
        reverse=True,
    )

    return critical_projects[:limit]


def get_sector_analytics(
    db: Session,
):
    """
    Get latest project risk statistics grouped by sector.
    """

    predictions = (
        db.query(Prediction)
        .join(Project, Prediction.project_id == Project.project_id)
        .order_by(
            Prediction.project_id.asc(),
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .all()
    )

    latest_by_project = {}

    for prediction in predictions:
        if prediction.project_id not in latest_by_project:
            latest_by_project[prediction.project_id] = prediction

    sector_data = {}

    for prediction in latest_by_project.values():

        project = (
            db.query(Project)
            .filter(Project.project_id == prediction.project_id)
            .first()
        )

        if not project:
            continue

        sector = project.sector or "Unknown"

        if sector not in sector_data:
            sector_data[sector] = {
                "total_projects": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "risk_scores": [],
            }

        data = sector_data[sector]

        data["total_projects"] += 1

        tier = (
            prediction.risk_tier.lower()
            if prediction.risk_tier
            else None
        )

        if tier in ["critical", "high", "medium", "low"]:
            data[tier] += 1

        if prediction.composite_risk_score is not None:
            data["risk_scores"].append(
                float(prediction.composite_risk_score)
            )

    results = []

    for sector, data in sector_data.items():

        scores = data.pop("risk_scores")

        average_risk_score = (
            sum(scores) / len(scores)
            if scores
            else None
        )

        results.append(
            {
                "sector": sector,
                "total_projects": data["total_projects"],
                "critical": data["critical"],
                "high": data["high"],
                "medium": data["medium"],
                "low": data["low"],
                "average_composite_risk_score": average_risk_score,
            }
        )

    results.sort(
        key=lambda x: (
            x["average_composite_risk_score"]
            if x["average_composite_risk_score"] is not None
            else -1
        ),
        reverse=True,
    )

    return results


def get_state_analytics(
    db: Session,
):
    """
    Get latest project risk statistics grouped by state.
    """

    predictions = (
        db.query(Prediction)
        .join(Project, Prediction.project_id == Project.project_id)
        .order_by(
            Prediction.project_id.asc(),
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .all()
    )

    latest_by_project = {}

    for prediction in predictions:
        if prediction.project_id not in latest_by_project:
            latest_by_project[prediction.project_id] = prediction

    state_data = {}

    for prediction in latest_by_project.values():

        project = (
            db.query(Project)
            .filter(Project.project_id == prediction.project_id)
            .first()
        )

        if not project:
            continue

        state = project.state or "Unknown"

        if state not in state_data:
            state_data[state] = {
                "total_projects": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "risk_scores": [],
            }

        data = state_data[state]

        data["total_projects"] += 1

        tier = (
            prediction.risk_tier.lower()
            if prediction.risk_tier
            else None
        )

        if tier in ["critical", "high", "medium", "low"]:
            data[tier] += 1

        if prediction.composite_risk_score is not None:
            data["risk_scores"].append(
                float(prediction.composite_risk_score)
            )

    results = []

    for state, data in state_data.items():

        scores = data.pop("risk_scores")

        average_risk_score = (
            sum(scores) / len(scores)
            if scores
            else None
        )

        results.append(
            {
                "state": state,
                "total_projects": data["total_projects"],
                "critical": data["critical"],
                "high": data["high"],
                "medium": data["medium"],
                "low": data["low"],
                "average_composite_risk_score": average_risk_score,
            }
        )

    results.sort(
        key=lambda x: (
            x["average_composite_risk_score"]
            if x["average_composite_risk_score"] is not None
            else -1
        ),
        reverse=True,
    )

    return results


def get_risk_trends(
    db: Session,
    limit: int = 12,
):
    """
    Get historical portfolio-level risk trends.
    """

    predictions = (
        db.query(Prediction)
        .order_by(
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .all()
    )

    monthly_data = {}

    for prediction in predictions:

        month = prediction.report_month

        if month not in monthly_data:
            monthly_data[month] = {
                "scores": [],
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }

        data = monthly_data[month]

        if prediction.composite_risk_score is not None:
            data["scores"].append(
                float(prediction.composite_risk_score)
            )

        tier = (
            prediction.risk_tier.lower()
            if prediction.risk_tier
            else None
        )

        if tier in ["critical", "high", "medium", "low"]:
            data[tier] += 1

    results = []

    for month, data in monthly_data.items():

        scores = data["scores"]

        average_risk_score = (
            sum(scores) / len(scores)
            if scores
            else None
        )

        results.append(
            {
                "report_month": month,
                "average_composite_risk_score": average_risk_score,
                "critical": data["critical"],
                "high": data["high"],
                "medium": data["medium"],
                "low": data["low"],
            }
        )

    results.sort(
        key=lambda x: x["report_month"],
        reverse=True,
    )

    return results[:limit]