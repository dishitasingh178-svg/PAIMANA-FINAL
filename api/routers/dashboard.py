from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from api.models.models import Project, ProjectUpdate, Prediction, Alert
from api.schemas.dashboard import (
    DashboardSummaryResponse,
    HighRiskProjectMapItem,
    RiskDistributionResponse,
    AlertItem,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


class SectorAnalyticsResponse(BaseModel):
    labels: List[str]
    critical: List[int]
    high: List[int]
    medium: List[int]


STATE_COORDINATES = {
    "TAMIL NADU": (11.1271, 78.6569),
    "MAHARASHTRA": (19.7515, 75.7139),
    "UTTAR PRADESH": (26.8467, 80.9462),
    "GUJARAT": (22.2587, 71.1924),
    "KARNATAKA": (15.3173, 75.7139),
    "WEST BENGAL": (22.9868, 87.8550),
    "ODISHA": (20.9517, 85.0985),
    "ANDHRA PRADESH": (15.9129, 79.7400),
    "JHARKHAND": (23.6102, 85.2799),
    "CHHATTISGARH": (21.2787, 81.8661),
    "MADHYA PRADESH": (22.9734, 78.6569),
    "RAJASTHAN": (27.0238, 74.2179),
    "BIHAR": (25.0961, 85.3131),
    "DELHI": (28.7041, 77.1025),
    "ASSAM": (26.2006, 92.9376),
    "PUNJAB": (31.1471, 75.3412),
    "HARYANA": (29.0588, 76.0856),
    "KERALA": (10.8505, 76.2711),
    "CENTRAL": (22.5937, 78.9629),
}


def _latest_updates(db: Session):
    """
    Return project updates ordered from newest to oldest for each project.

    The first occurrence of each project is therefore its latest
    available monthly snapshot.
    """
    return (
        db.query(ProjectUpdate)
        .order_by(
            ProjectUpdate.project_id,
            ProjectUpdate.report_month.desc(),
            ProjectUpdate.id.desc(),
        )
        .all()
    )


def _latest_predictions(db: Session):
    """
    Return the latest stored prediction for every project.
    """
    rows = (
        db.query(Prediction)
        .order_by(
            Prediction.project_id,
            Prediction.generated_at.desc(),
            Prediction.prediction_id.desc(),
        )
        .all()
    )

    result = {}

    for row in rows:
        pid = str(row.project_id).strip()
        result.setdefault(pid, row)

    return result


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    # ---------------------------------------------------------
    # 1. Total projects
    # ---------------------------------------------------------
    total_projects = int(
        db.query(func.count(Project.project_id)).scalar() or 0
    )

    # ---------------------------------------------------------
    # 2. Latest prediction for each project
    # ---------------------------------------------------------
    predictions = _latest_predictions(db)

    high_risk = sum(
        1
        for prediction in predictions.values()
        if float(prediction.composite_risk_score or 0) >= 50
    )

    # ---------------------------------------------------------
    # 3. Load projects and latest monthly update
    # ---------------------------------------------------------
    projects = {
        str(project.project_id).strip(): project
        for project in db.query(Project).all()
    }

    latest_updates = {}

    for update in _latest_updates(db):
        pid = str(update.project_id).strip()
        latest_updates.setdefault(pid, update)

    # ---------------------------------------------------------
    # 4. Calculate financial totals
    #
    # Original cost is stored on Project.
    # Revised cost and cumulative expenditure are stored
    # on the latest ProjectUpdate.
    # ---------------------------------------------------------
    original_total = 0.0
    revised_total = 0.0
    expenditure_total = 0.0

    delayed = 0

    for pid, project in projects.items():

        # Original project cost
        original_total += float(
            project.original_cost_crore or 0.0
        )

        update = latest_updates.get(pid)

        if not update:
            continue

        # Latest revised cost
        revised_total += float(
            update.revised_cost_crore or 0.0
        )

        # Latest cumulative expenditure
        expenditure_total += float(
            update.cumulative_expenditure_crore or 0.0
        )

        # -----------------------------------------------------
        # Delay calculation
        # -----------------------------------------------------
        revised_date = (
            update.revised_commissioning_date
            or update.anticipated_commissioning_date
        )

        if (
            project.original_commissioning_date
            and revised_date
            and revised_date > project.original_commissioning_date
        ):
            delayed += 1

    # ---------------------------------------------------------
    # 5. Convert crore → lakh crore
    #
    # 1 lakh crore = 100,000 crore
    # ---------------------------------------------------------
    original_lakh_cr = original_total / 100000.0
    revised_lakh_cr = revised_total / 100000.0
    expenditure_lakh_cr = expenditure_total / 100000.0

    # ---------------------------------------------------------
    # 6. Return database-derived statistics
    # ---------------------------------------------------------
    return DashboardSummaryResponse(
        total_projects=total_projects,
        high_risk_count=high_risk,
        delayed_count=delayed,
        original_cost_lakh_cr=str(
            round(original_lakh_cr, 2)
        ),
        revised_cost_lakh_cr=str(
            round(revised_lakh_cr, 2)
        ),
        expenditure_lakh_cr=str(
            round(expenditure_lakh_cr, 2)
        ),
    )


@router.get(
    "/ongoing-high-risk",
    response_model=List[HighRiskProjectMapItem],
)
def get_ongoing_high_risk(db: Session = Depends(get_db)):

    predictions = _latest_predictions(db)

    projects = {
        str(project.project_id).strip(): project
        for project in db.query(Project).all()
    }

    latest_updates = {}

    for update in _latest_updates(db):
        pid = str(update.project_id).strip()
        latest_updates.setdefault(pid, update)

    items = []

    for pid, prediction in predictions.items():

        score = float(
            prediction.composite_risk_score or 0
        )

        if score < 50 or pid not in projects:
            continue

        project = projects[pid]
        update = latest_updates.get(pid)

        revised_date = (
            update.revised_commissioning_date
            if update
            else None
        )

        delay = 0

        if (
            project.original_commissioning_date
            and revised_date
        ):
            delay = max(
                0,
                (
                    revised_date.year
                    - project.original_commissioning_date.year
                )
                * 12
                + (
                    revised_date.month
                    - project.original_commissioning_date.month
                ),
            )

        state_key = str(
            project.state or "CENTRAL"
        ).strip().upper()

        lat, lng = STATE_COORDINATES.get(
            state_key,
            STATE_COORDINATES["CENTRAL"],
        )

        items.append(
            HighRiskProjectMapItem(
                project_id=pid,
                project_name=(
                    project.project_name
                    or f"Project #{pid}"
                ),
                status=str(
                    prediction.risk_tier
                    or "ELEVATED"
                ).upper(),
                sector=(
                    project.sector
                    or "Infrastructure"
                ),
                risk_score=round(score, 2),
                delay_months=int(delay),
                lat=lat,
                lng=lng,
            )
        )

    return sorted(
        items,
        key=lambda item: item.risk_score,
        reverse=True,
    )[:100]


@router.get(
    "/risk-distribution",
    response_model=RiskDistributionResponse,
)
def get_risk_distribution(
    db: Session = Depends(get_db),
):
    predictions = _latest_predictions(db).values()

    counts = {
        "low": 0,
        "watch": 0,
        "elevated": 0,
        "critical": 0,
    }

    for prediction in predictions:

        score = float(
            prediction.composite_risk_score or 0
        )

        if score >= 75:
            counts["critical"] += 1

        elif score >= 50:
            counts["elevated"] += 1

        elif score >= 25:
            counts["watch"] += 1

        else:
            counts["low"] += 1

    return RiskDistributionResponse(**counts)


@router.get(
    "/alerts",
    response_model=List[AlertItem],
)
def get_alerts(db: Session = Depends(get_db)):

    rows = (
        db.query(Alert, Project)
        .join(
            Project,
            Project.project_id == Alert.project_id,
        )
        .filter(
            Alert.is_resolved.is_(False),
            func.coalesce(Alert.status, "NEW") != "DISMISSED",
        )
        .order_by(
            Alert.triggered_at.desc()
        )
        .limit(20)
        .all()
    )

    return [
        AlertItem(
            project_name=(
                project.project_name
                or f"Project #{alert.project_id}"
            ),
            message=alert.message,
            severity=alert.severity,
        )
        for alert, project in rows
    ]


@router.get(
    "/sector-breakdown",
    response_model=SectorAnalyticsResponse,
)
def get_sector_breakdown(
    db: Session = Depends(get_db),
):

    predictions = _latest_predictions(db)

    projects = {
        str(project.project_id).strip(): project
        for project in db.query(Project).all()
    }

    buckets = {}

    for pid, prediction in predictions.items():

        project = projects.get(pid)

        if not project:
            continue

        sector = project.sector or "Unknown"

        score = float(
            prediction.composite_risk_score or 0
        )

        bucket = buckets.setdefault(
            sector,
            {
                "critical": 0,
                "high": 0,
                "medium": 0,
            },
        )

        if score >= 75:
            bucket["critical"] += 1

        elif score >= 50:
            bucket["high"] += 1

        elif score >= 25:
            bucket["medium"] += 1

    labels = sorted(
        buckets,
        key=lambda sector: sum(
            buckets[sector].values()
        ),
        reverse=True,
    )[:10]

    return SectorAnalyticsResponse(
        labels=labels,
        critical=[
            buckets[sector]["critical"]
            for sector in labels
        ],
        high=[
            buckets[sector]["high"]
            for sector in labels
        ],
        medium=[
            buckets[sector]["medium"]
            for sector in labels
        ],
    )
