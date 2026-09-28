from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text, true
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from database import get_db
from api.services.state_names import canonical_state
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


# Only the columns the dashboard endpoints read. Rows keep the same attribute
# names as the ORM objects, so the endpoint code below is unchanged; loading
# full ORM objects for every project was most of the remaining cost.
_PREDICTION_COLUMNS = (
    Prediction.project_id,
    Prediction.composite_risk_score,
    Prediction.risk_tier,
)
_PROJECT_COLUMNS = (
    Project.project_id,
    Project.project_name,
    Project.sector,
    Project.state,
    Project.original_cost_crore,
    Project.original_commissioning_date,
)
_UPDATE_COLUMNS = (
    ProjectUpdate.project_id,
    ProjectUpdate.revised_cost_crore,
    ProjectUpdate.cumulative_expenditure_crore,
    ProjectUpdate.revised_commissioning_date,
    ProjectUpdate.anticipated_commissioning_date,
)


def _projects(db: Session, project_ids=None):
    """Dashboard columns of all projects, or only of `project_ids`."""
    query = db.query(*_PROJECT_COLUMNS)
    if project_ids is not None:
        if not project_ids:
            return []
        query = query.filter(Project.project_id.in_(project_ids))
    return query.all()


def _latest_updates(db: Session, project_ids=None):
    """
    Return the latest monthly update of each project (one row per project).

    (project_id, report_month) is unique, so "latest" is simply the highest
    report_month. On PostgreSQL this is a DISTINCT ON read that walks the
    existing (project_id, report_month) index backwards, instead of loading
    every historical update and keeping the first one per project in Python.
    Callers still take the first occurrence per project, so any database
    returns the same result.
    """
    postgres = db.get_bind().dialect.name == "postgresql"

    if project_ids is not None and postgres:
        if not project_ids:
            return []
        # A subset of projects: one backward index probe per project
        # (LIMIT 1), instead of gathering and sorting their whole history.
        latest = (
            select(*_UPDATE_COLUMNS)
            .where(ProjectUpdate.project_id == Project.project_id)
            .order_by(ProjectUpdate.report_month.desc())
            .limit(1)
            .lateral("latest_update")
        )
        return db.execute(
            select(*latest.c)
            .select_from(Project)
            .join(latest, true())
            .where(Project.project_id.in_(project_ids))
        ).all()

    query = db.query(*_UPDATE_COLUMNS)

    if project_ids is not None:
        if not project_ids:
            return []
        query = query.filter(ProjectUpdate.project_id.in_(project_ids))

    if postgres:
        return (
            query
            .ext(distinct_on(ProjectUpdate.project_id))
            .order_by(
                ProjectUpdate.project_id.desc(),
                ProjectUpdate.report_month.desc(),
            )
            .all()
        )

    return (
        query
        .order_by(
            ProjectUpdate.project_id,
            ProjectUpdate.report_month.desc(),
            ProjectUpdate.id.desc(),
        )
        .all()
    )


def _latest_predictions(db: Session):
    """
    Return the latest stored prediction for every project (most recently
    generated, as before), keyed by project and ordered by project_id.
    """
    query = db.query(*_PREDICTION_COLUMNS)

    if db.get_bind().dialect.name == "postgresql":
        query = query.ext(distinct_on(Prediction.project_id))

    rows = (
        query
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


def _summary_totals_python(db: Session):
    """Portable aggregation (non-PostgreSQL databases, e.g. the SQLite tests)."""
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
        for project in _projects(db)
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
    return high_risk, original_total, revised_total, expenditure_total, delayed


# Same rules as _summary_totals_python, aggregated in PostgreSQL: one row back
# instead of every project and its latest update.
_SUMMARY_TOTALS_SQL = text("""
WITH latest_prediction AS (
    SELECT DISTINCT ON (project_id) composite_risk_score
    FROM predictions
    ORDER BY project_id, generated_at DESC, prediction_id DESC
)
SELECT
    (SELECT count(*) FROM latest_prediction
      WHERE coalesce(composite_risk_score, 0) >= 50)            AS high_risk,
    coalesce(sum(p.original_cost_crore), 0)                     AS original_total,
    coalesce(sum(u.revised_cost_crore), 0)                      AS revised_total,
    coalesce(sum(u.cumulative_expenditure_crore), 0)            AS expenditure_total,
    count(*) FILTER (
        WHERE p.original_commissioning_date IS NOT NULL
          AND coalesce(u.revised_commissioning_date, u.anticipated_commissioning_date)
              > p.original_commissioning_date)                  AS delayed
FROM projects p
LEFT JOIN LATERAL (
    SELECT revised_cost_crore, cumulative_expenditure_crore,
           revised_commissioning_date, anticipated_commissioning_date
    FROM project_updates x
    WHERE x.project_id = p.project_id
    ORDER BY x.report_month DESC
    LIMIT 1
) u ON true
""")


def _summary_totals(db: Session):
    if db.get_bind().dialect.name != "postgresql":
        return _summary_totals_python(db)
    row = db.execute(_SUMMARY_TOTALS_SQL).one()
    return (
        int(row.high_risk),
        float(row.original_total),
        float(row.revised_total),
        float(row.expenditure_total),
        int(row.delayed),
    )


@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    # ---------------------------------------------------------
    # 1. Total projects
    # ---------------------------------------------------------
    total_projects = int(
        db.query(func.count(Project.project_id)).scalar() or 0
    )

    # ---------------------------------------------------------
    # 2-4. Latest predictions, latest updates and financial totals
    # ---------------------------------------------------------
    (
        high_risk,
        original_total,
        revised_total,
        expenditure_total,
        delayed,
    ) = _summary_totals(db)

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

    # Only projects whose latest score is >= 50 can appear on the map, so
    # project and update rows are fetched for those candidates alone.
    candidates = [
        pid
        for pid, prediction in predictions.items()
        if float(prediction.composite_risk_score or 0) >= 50
    ]

    projects = {
        str(project.project_id).strip(): project
        for project in _projects(db, candidates)
    }

    latest_updates = {}

    for update in _latest_updates(db, candidates):
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

        state_key = canonical_state(project.state)
        coordinates = STATE_COORDINATES.get(state_key)
        # Missing/unrecognized/multi-state locations have no defensible pin.
        if coordinates is None:
            continue
        lat, lng = coordinates

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
        for project in _projects(db)
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
