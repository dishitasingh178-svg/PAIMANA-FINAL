from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.models.models import Alert, Prediction, Project, ProjectUpdate


# ============================================================
# CENTRALIZED ALERT THRESHOLDS
# ============================================================

# ML composite score
ML_WATCH_SCORE = 25.0
ML_ELEVATED_SCORE = 50.0
ML_CRITICAL_SCORE = 75.0

# Risk deterioration
RISK_DETERIORATION_WATCH = 10.0
RISK_DETERIORATION_ELEVATED = 20.0

# Cost escalation
COST_ESCALATION_WATCH_PCT = 8.0
COST_ESCALATION_ELEVATED_PCT = 15.0

# Revised cost vs original cost
REVISED_VS_ORIGINAL_WATCH_PCT = 10.0
REVISED_VS_ORIGINAL_ELEVATED_PCT = 20.0

# Expenditure acceleration
EXPENDITURE_ACCELERATION_WATCH_RATIO = 1.5
EXPENDITURE_ACCELERATION_ELEVATED_RATIO = 2.0
EXPENDITURE_ACCELERATION_MIN_BASELINE_PCT = 1.0

# Expenditure vs milestone progress
EXPENDITURE_PROGRESS_GAP_WATCH = 15.0
EXPENDITURE_PROGRESS_GAP_ELEVATED = 25.0

# Milestone stagnation
MILESTONE_STAGNATION_WATCH_PERIODS = 4
MILESTONE_STAGNATION_ELEVATED_PERIODS = 6
MILESTONE_STAGNATION_MIN_EXPENDITURE_PCT = 20.0

# Schedule delay
SCHEDULE_DELAY_WATCH_MONTHS = 3.0
SCHEDULE_DELAY_ELEVATED_MONTHS = 6.0

SCHEDULE_DELAY_INCREASE_WATCH = 1.0
SCHEDULE_DELAY_INCREASE_ELEVATED = 3.0

SCHEDULE_DATE_SHIFT_WATCH_DAYS = 30
SCHEDULE_DATE_SHIFT_ELEVATED_DAYS = 90


@dataclass
class CandidateAlert:
    alert_type: str
    severity: str
    message: str


# ============================================================
# GENERAL HELPERS
# ============================================================

def _num(value: Any) -> Optional[float]:
    """
    Convert Decimal / integer / float / string safely to float.

    None stays None.
    Missing data is NEVER treated as zero.
    """
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct_change(
    current: Optional[float],
    previous: Optional[float],
) -> Optional[float]:

    if current is None or previous is None:
        return None

    if previous <= 0:
        return None

    return ((current - previous) / previous) * 100.0


def _severity_from_percentage(
    value: float,
    watch_threshold: float,
    elevated_threshold: float,
) -> str:

    if value >= elevated_threshold:
        return "ELEVATED"

    if value >= watch_threshold:
        return "WATCH"

    return "WATCH"


# ============================================================
# DATABASE HELPERS
# ============================================================

def _get_updates(
    db: Session,
    project_id: str,
    target_month: str,
    limit: int = 8,
) -> list[ProjectUpdate]:

    return (
        db.query(ProjectUpdate)
        .filter(
            ProjectUpdate.project_id == project_id,
            ProjectUpdate.report_month <= target_month,
        )
        .order_by(ProjectUpdate.report_month.desc())
        .limit(limit)
        .all()
    )


def _get_previous_predictions(
    db: Session,
    project_id: str,
    target_month: str,
    limit: int = 6,
) -> list[Prediction]:

    rows = (
        db.query(Prediction)
        .filter(
            Prediction.project_id == project_id,
            Prediction.report_month < target_month,
        )
        .order_by(
            Prediction.report_month.desc(),
            Prediction.generated_at.desc(),
        )
        .limit(limit * 2)
        .all()
    )

    result = []
    seen_months = set()

    for row in rows:

        month = str(row.report_month).strip()

        if month in seen_months:
            continue

        seen_months.add(month)
        result.append(row)

        if len(result) >= limit:
            break

    return result


# ============================================================
# COST BASELINE
# ============================================================

def _get_cost_baseline(
    project: Project,
    update: ProjectUpdate,
) -> Optional[float]:

    # Prefer revised cost when available.
    revised = _num(update.revised_cost_crore)

    if revised is not None and revised > 0:
        return revised

    # Otherwise use anticipated cost.
    anticipated = _num(update.anticipated_cost_crore)

    if anticipated is not None and anticipated > 0:
        return anticipated

    # Finally use original approved cost.
    original = _num(project.original_cost_crore)

    if original is not None and original > 0:
        return original

    return None


# ============================================================
# ML RISK WARNING
# ============================================================

def _check_ml_risk(
    project_id: str,
    target_month: str,
    prediction_result: dict[str, Any],
) -> Optional[CandidateAlert]:

    score = _num(
        prediction_result.get("composite_risk_score")
    )

    tier = str(
        prediction_result.get("risk_tier") or ""
    ).upper()

    if score is None:
        return None

    if score >= ML_CRITICAL_SCORE or tier == "CRITICAL":

        severity = "CRITICAL"

    elif score >= ML_ELEVATED_SCORE or tier == "ELEVATED":

        severity = "ELEVATED"

    elif score >= ML_WATCH_SCORE or tier == "WATCH":

        severity = "WATCH"

    else:

        return None

    return CandidateAlert(
        alert_type="ML_RISK_WARNING",
        severity=severity,
        message=(
            f"[{target_month}] ML risk warning: "
            f"composite risk score is {score:.1f}/100 "
            f"({tier})."
        ),
    )


# ============================================================
# RISK DETERIORATION
# ============================================================

def _check_risk_deterioration(
    db: Session,
    project_id: str,
    target_month: str,
    prediction_result: dict[str, Any],
) -> Optional[CandidateAlert]:

    current_score = _num(
        prediction_result.get("composite_risk_score")
    )

    if current_score is None:
        return None

    previous = _get_previous_predictions(
        db,
        project_id,
        target_month,
    )

    if not previous:
        return None

    previous_score = _num(
        previous[0].composite_risk_score
    )

    if previous_score is None:
        return None

    increase = current_score - previous_score

    if increase >= RISK_DETERIORATION_ELEVATED:

        severity = "ELEVATED"

    elif increase >= RISK_DETERIORATION_WATCH:

        severity = "WATCH"

    else:

        return None

    return CandidateAlert(
        alert_type="RISK_DETERIORATION",
        severity=severity,
        message=(
            f"[{target_month}] Risk deterioration detected: "
            f"composite risk increased from "
            f"{previous_score:.1f} to {current_score:.1f} "
            f"(+{increase:.1f} points) since "
            f"{previous[0].report_month}."
        ),
    )


# ============================================================
# COST ESCALATION
# ============================================================

def _check_cost_escalation(
    project: Project,
    updates: list[ProjectUpdate],
    target_month: str,
) -> list[CandidateAlert]:

    if not updates:
        return []

    current = updates[0]
    alerts = []

    # --------------------------------------------------------
    # Primary signal:
    # anticipated cost is available in essentially all rows
    # --------------------------------------------------------

    current_cost = _num(
        current.anticipated_cost_crore
    )

    previous_cost = None
    previous_month = None

    for row in updates[1:]:

        value = _num(
            row.anticipated_cost_crore
        )

        if value is not None and value > 0:

            previous_cost = value
            previous_month = row.report_month
            break

    change = _pct_change(
        current_cost,
        previous_cost,
    )

    if change is not None and change >= COST_ESCALATION_WATCH_PCT:

        severity = _severity_from_percentage(
            change,
            COST_ESCALATION_WATCH_PCT,
            COST_ESCALATION_ELEVATED_PCT,
        )

        alerts.append(
            CandidateAlert(
                alert_type="COST_ESCALATION",
                severity=severity,
                message=(
                    f"[{target_month}] Anticipated cost increased "
                    f"from ₹{previous_cost:,.2f} crore to "
                    f"₹{current_cost:,.2f} crore "
                    f"(+{change:.1f}%) since "
                    f"{previous_month}."
                ),
            )
        )

    # --------------------------------------------------------
    # Secondary signal:
    # revised cost vs original approved cost
    # --------------------------------------------------------

    revised = _num(
        current.revised_cost_crore
    )

    original = _num(
        project.original_cost_crore
    )

    revised_change = _pct_change(
        revised,
        original,
    )

    if (
        revised_change is not None
        and revised_change >= REVISED_VS_ORIGINAL_WATCH_PCT
    ):

        severity = _severity_from_percentage(
            revised_change,
            REVISED_VS_ORIGINAL_WATCH_PCT,
            REVISED_VS_ORIGINAL_ELEVATED_PCT,
        )

        alerts.append(
            CandidateAlert(
                alert_type="COST_ESCALATION",
                severity=severity,
                message=(
                    f"[{target_month}] Revised cost is "
                    f"₹{revised:,.2f} crore versus original "
                    f"cost of ₹{original:,.2f} crore "
                    f"(+{revised_change:.1f}%)."
                ),
            )
        )

    return alerts


# ============================================================
# EXPENDITURE ACCELERATION
# ============================================================

def _check_expenditure_acceleration(
    project: Project,
    updates: list[ProjectUpdate],
    target_month: str,
) -> Optional[CandidateAlert]:

    if len(updates) < 5:
        return None

    values = [
        _num(row.cumulative_expenditure_crore)
        for row in updates[:5]
    ]

    if any(value is None for value in values):
        return None

    current = values[0]
    previous_1 = values[1]
    previous_2 = values[2]
    previous_3 = values[3]
    previous_4 = values[4]

    current_delta = current - previous_1

    historical_deltas = [
        previous_1 - previous_2,
        previous_2 - previous_3,
        previous_3 - previous_4,
    ]

    positive_deltas = [
        value
        for value in historical_deltas
        if value > 0
    ]

    if current_delta <= 0 or not positive_deltas:
        return None

    average_previous_delta = (
        sum(positive_deltas)
        / len(positive_deltas)
    )

    if average_previous_delta <= 0:
        return None

    acceleration_ratio = (
        current_delta
        / average_previous_delta
    )

    baseline = _get_cost_baseline(
        project,
        updates[0],
    )

    if baseline is None:
        return None

    current_delta_pct = (
        current_delta / baseline
    ) * 100.0

    if (
        acceleration_ratio
        < EXPENDITURE_ACCELERATION_WATCH_RATIO
    ):
        return None

    if (
        current_delta_pct
        < EXPENDITURE_ACCELERATION_MIN_BASELINE_PCT
    ):
        return None

    if (
        acceleration_ratio
        >= EXPENDITURE_ACCELERATION_ELEVATED_RATIO
    ):
        severity = "ELEVATED"
    else:
        severity = "WATCH"

    return CandidateAlert(
        alert_type="EXPENDITURE_ACCELERATION",
        severity=severity,
        message=(
            f"[{target_month}] Expenditure accelerated: "
            f"latest increase was ₹{current_delta:,.2f} crore, "
            f"about {acceleration_ratio:.1f}× the average "
            f"increase across previous reporting periods."
        ),
    )


# ============================================================
# EXPENDITURE VS MILESTONE PROGRESS
# ============================================================

def _check_expenditure_progress_gap(
    project: Project,
    update: ProjectUpdate,
    target_month: str,
) -> Optional[CandidateAlert]:

    expenditure = _num(
        update.cumulative_expenditure_crore
    )

    milestones_achieved = _num(
        update.milestones_achieved
    )

    milestones_total = _num(
        update.milestones_total
    )

    baseline = _get_cost_baseline(
        project,
        update,
    )

    if any(
        value is None
        for value in (
            expenditure,
            milestones_achieved,
            milestones_total,
            baseline,
        )
    ):
        return None

    if milestones_total <= 0 or baseline <= 0:
        return None

    expenditure_progress = (
        expenditure / baseline
    ) * 100.0

    milestone_progress = (
        milestones_achieved
        / milestones_total
    ) * 100.0

    gap = (
        expenditure_progress
        - milestone_progress
    )

    if gap < EXPENDITURE_PROGRESS_GAP_WATCH:
        return None

    if gap >= EXPENDITURE_PROGRESS_GAP_ELEVATED:
        severity = "ELEVATED"
    else:
        severity = "WATCH"

    return CandidateAlert(
        alert_type="EXPENDITURE_PROGRESS_GAP",
        severity=severity,
        message=(
            f"[{target_month}] Expenditure is substantially "
            f"ahead of recorded milestone progress: "
            f"expenditure is {expenditure_progress:.1f}% "
            f"of the selected cost baseline versus "
            f"{milestone_progress:.1f}% milestones achieved "
            f"(gap {gap:.1f} percentage points)."
        ),
    )


# ============================================================
# MILESTONE STAGNATION
# ============================================================

def _check_milestone_stagnation(
    project: Project,
    updates: list[ProjectUpdate],
    target_month: str,
) -> Optional[CandidateAlert]:

    if len(updates) < MILESTONE_STAGNATION_WATCH_PERIODS:
        return None

    achieved = [
        _num(row.milestones_achieved)
        for row in updates
    ]

    totals = [
        _num(row.milestones_total)
        for row in updates
    ]

    if any(
        value is None
        for value in achieved[:MILESTONE_STAGNATION_ELEVATED_PERIODS]
    ):
        return None

    if any(
        value is None
        for value in totals[:MILESTONE_STAGNATION_WATCH_PERIODS]
    ):
        return None

    current = updates[0]

    total = _num(
        current.milestones_total
    )

    expenditure = _num(
        current.cumulative_expenditure_crore
    )

    baseline = _get_cost_baseline(
        project,
        current,
    )

    if (
        total is None
        or total <= 0
        or expenditure is None
        or baseline is None
    ):
        return None

    expenditure_progress = (
        expenditure / baseline
    ) * 100.0

    # Avoid flagging very early projects.
    if (
        expenditure_progress
        < MILESTONE_STAGNATION_MIN_EXPENDITURE_PCT
    ):
        return None

    watch_values = achieved[
        :MILESTONE_STAGNATION_WATCH_PERIODS
    ]

    if len(set(watch_values)) != 1:
        return None

    periods = MILESTONE_STAGNATION_WATCH_PERIODS

    if len(achieved) >= MILESTONE_STAGNATION_ELEVATED_PERIODS:

        elevated_values = achieved[
            :MILESTONE_STAGNATION_ELEVATED_PERIODS
        ]

        if len(set(elevated_values)) == 1:
            periods = MILESTONE_STAGNATION_ELEVATED_PERIODS

    if periods >= MILESTONE_STAGNATION_ELEVATED_PERIODS:
        severity = "ELEVATED"
    else:
        severity = "WATCH"

    current_achieved = int(
        watch_values[0]
    )

    return CandidateAlert(
        alert_type="MILESTONE_STAGNATION",
        severity=severity,
        message=(
            f"[{target_month}] No milestone advancement "
            f"recorded across the last {periods} "
            f"reporting periods. Milestones remain "
            f"{current_achieved}/{int(total)}, while "
            f"expenditure is {expenditure_progress:.1f}% "
            f"of the selected cost baseline."
        ),
    )


# ============================================================
# SCHEDULE SLIPPAGE
# ============================================================

def _check_schedule_slippage(
    updates: list[ProjectUpdate],
    target_month: str,
) -> Optional[CandidateAlert]:

    if not updates:
        return None

    current = updates[0]

    previous = (
        updates[1]
        if len(updates) > 1
        else None
    )

    # Prefer revised delay if available.
    current_delay = _num(
        current.delay_revised_months
    )

    previous_delay = (
        _num(previous.delay_revised_months)
        if previous
        else None
    )

    delay_source = "revised"

    # Fall back to original delay.
    if current_delay is None:

        current_delay = _num(
            current.delay_original_months
        )

        previous_delay = (
            _num(previous.delay_original_months)
            if previous
            else None
        )

        delay_source = "original"

    if current_delay is not None:

        if (
            current_delay
            >= SCHEDULE_DELAY_ELEVATED_MONTHS
        ):

            return CandidateAlert(
                alert_type="SCHEDULE_SLIPPAGE",
                severity="ELEVATED",
                message=(
                    f"[{target_month}] Schedule slippage "
                    f"is {current_delay:.1f} months based "
                    f"on {delay_source} delay data."
                ),
            )

        if (
            current_delay
            >= SCHEDULE_DELAY_WATCH_MONTHS
        ):

            return CandidateAlert(
                alert_type="SCHEDULE_SLIPPAGE",
                severity="WATCH",
                message=(
                    f"[{target_month}] Schedule slippage "
                    f"is {current_delay:.1f} months based "
                    f"on {delay_source} delay data."
                ),
            )

        if previous_delay is not None:

            increase = (
                current_delay
                - previous_delay
            )

            if (
                increase
                >= SCHEDULE_DELAY_INCREASE_ELEVATED
            ):

                return CandidateAlert(
                    alert_type="SCHEDULE_SLIPPAGE",
                    severity="ELEVATED",
                    message=(
                        f"[{target_month}] Schedule delay "
                        f"increased by {increase:.1f} months, "
                        f"from {previous_delay:.1f} to "
                        f"{current_delay:.1f} months."
                    ),
                )

            if (
                increase
                >= SCHEDULE_DELAY_INCREASE_WATCH
            ):

                return CandidateAlert(
                    alert_type="SCHEDULE_SLIPPAGE",
                    severity="WATCH",
                    message=(
                        f"[{target_month}] Schedule delay "
                        f"increased by {increase:.1f} months, "
                        f"from {previous_delay:.1f} to "
                        f"{current_delay:.1f} months."
                    ),
                )

    # --------------------------------------------------------
    # Commissioning date movement
    # --------------------------------------------------------

    def get_commissioning_date(
        row: ProjectUpdate,
    ) -> Optional[date]:

        return (
            row.revised_commissioning_date
            or row.anticipated_commissioning_date
        )

    current_date = get_commissioning_date(
        current
    )

    previous_date = (
        get_commissioning_date(previous)
        if previous
        else None
    )

    if current_date and previous_date:

        shift_days = (
            current_date - previous_date
        ).days

        if (
            shift_days
            >= SCHEDULE_DATE_SHIFT_ELEVATED_DAYS
        ):

            return CandidateAlert(
                alert_type="SCHEDULE_SLIPPAGE",
                severity="ELEVATED",
                message=(
                    f"[{target_month}] Anticipated "
                    f"commissioning moved later by "
                    f"{shift_days} days compared with "
                    f"the previous reporting period."
                ),
            )

        if (
            shift_days
            >= SCHEDULE_DATE_SHIFT_WATCH_DAYS
        ):

            return CandidateAlert(
                alert_type="SCHEDULE_SLIPPAGE",
                severity="WATCH",
                message=(
                    f"[{target_month}] Anticipated "
                    f"commissioning moved later by "
                    f"{shift_days} days compared with "
                    f"the previous reporting period."
                ),
            )

    return None


# ============================================================
# DEDUPLICATION
# ============================================================

def _save_alert_if_new(
    db: Session,
    project_id: str,
    candidate: CandidateAlert,
) -> Optional[Alert]:

    existing = (
        db.query(Alert)
        .filter(
            Alert.project_id == project_id,
            Alert.alert_type == candidate.alert_type,
            Alert.severity == candidate.severity,
            Alert.message == candidate.message,
            Alert.is_resolved.is_(False),
        )
        .first()
    )

    if existing:
        return None

    alert = Alert(
        project_id=project_id,
        alert_type=candidate.alert_type,
        severity=candidate.severity,
        message=candidate.message,
    )

    db.add(alert)

    return alert


# ============================================================
# MAIN ALERT ENGINE
# ============================================================

def generate_alerts(
    db: Session,
    project: Project,
    target_month: str,
    prediction_result: dict[str, Any],
) -> list[Alert]:

    project_id = str(
        project.project_id
    ).strip()

    target_month = str(
        target_month
    ).strip()[:7]

    updates = _get_updates(
        db,
        project_id,
        target_month,
    )

    if not updates:
        return []

    candidates: list[CandidateAlert] = []

    # 1. ML risk
    ml_alert = _check_ml_risk(
        project_id,
        target_month,
        prediction_result,
    )

    if ml_alert:
        candidates.append(ml_alert)

    # 2. Risk deterioration
    deterioration = _check_risk_deterioration(
        db,
        project_id,
        target_month,
        prediction_result,
    )

    if deterioration:
        candidates.append(deterioration)

    # 3. Cost escalation
    candidates.extend(
        _check_cost_escalation(
            project,
            updates,
            target_month,
        )
    )

    # 4. Expenditure acceleration
    expenditure_alert = (
        _check_expenditure_acceleration(
            project,
            updates,
            target_month,
        )
    )

    if expenditure_alert:
        candidates.append(
            expenditure_alert
        )

    # 5. Expenditure vs milestones
    progress_gap = (
        _check_expenditure_progress_gap(
            project,
            updates[0],
            target_month,
        )
    )

    if progress_gap:
        candidates.append(
            progress_gap
        )

    # 6. Milestone stagnation
    milestone_alert = (
        _check_milestone_stagnation(
            project,
            updates,
            target_month,
        )
    )

    if milestone_alert:
        candidates.append(
            milestone_alert
        )

    # 7. Schedule slippage
    schedule_alert = (
        _check_schedule_slippage(
            updates,
            target_month,
        )
    )

    if schedule_alert:
        candidates.append(
            schedule_alert
        )

    created: list[Alert] = []

    for candidate in candidates:

        alert = _save_alert_if_new(
            db,
            project_id,
            candidate,
        )

        if alert:
            created.append(alert)

    return created