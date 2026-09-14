import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from api.models.models import Project, ProjectUpdate

# ==============================================================================
# 1. ARTIFACT PATHS & FEATURE SPECIFICATIONS
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "..", "..", "ml_package")
FEATURE_COLUMNS_PATH = os.path.join(ARTIFACTS_DIR, "feature_columns.joblib")

BENCHMARK_LOOKUP_PATH = os.path.join(ARTIFACTS_DIR, "benchmark_lookups.parquet")
_BENCHMARK_DF = pd.read_parquet(BENCHMARK_LOOKUP_PATH) if os.path.exists(BENCHMARK_LOOKUP_PATH) else None

if os.path.exists(FEATURE_COLUMNS_PATH):
    FEATURE_COLUMNS = joblib.load(FEATURE_COLUMNS_PATH)
else:
    # Authoritative 47 features fallback from contract
    FEATURE_COLUMNS = [
        "month", "year", "sector", "state", "approval_year", "project_age",
        "original_duration_months", "duration_overrun_months", "original_cost_crore",
        "revised_cost_crore", "anticipated_cost_crore", "current_cost",
        "cumulative_expenditure_crore", "anticipated_delay_from_original",
        "remaining_org_months", "delay_revised_months", "delay_revisied_months",
        "milestones_achieved", "milestones_total", "milestone_completion_percentage",
        "milestone_data_reliable", "cost_revision_percentage", "anticipated_cost_percentage",
        "exp_vs_anti_prct", "exp_vs_org_prct", "exp_vs_rev_prct",
        "project_duration_elapsed_percentage", "cost_growth_3m", "cost_growth_6m",
        "cost_growth_12m", "expenditure_growth_3m", "expenditure_growth_6m",
        "expenditure_growth_12m", "schedule_change_3m", "schedule_change_6m",
        "schedule_change_12m", "milestone_progress_change_3m", "milestone_progress_change_6m",
        "milestone_progress_change_12m", "expenditure_progress_gap_org",
        "expenditure_progress_gap_anti", "cost_rebaseline_signal", "schedule_progress_mismatch",
        "early_phase_milestone_artifact", "agency_overrun_rate", "agency_project_count_as_of_T",
        "sector_overrun_rate"
    ]


# ==============================================================================
# 2. DATE & CALENDAR-MONTH ARITHMETIC UTILITIES
# ==============================================================================
def to_date(val: Any) -> Optional[date]:
    """Converts string, datetime, or date to datetime.date object."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    str_val = str(val).strip()
    if len(str_val) == 7:  # YYYY-MM
        str_val = f"{str_val}-01"
    try:
        return datetime.strptime(str_val, "%Y-%m-%d").date()
    except ValueError:
        return None


def months_between(d1: Optional[date], d2: Optional[date]) -> Optional[int]:
    """
    Calendar-month difference: (d1.year - d2.year) * 12 + (d1.month - d2.month)
    Returns None if either date is None.
    """
    if d1 is None or d2 is None:
        return None
    return (d1.year - d2.year) * 12 + (d1.month - d2.month)


def get_target_report_month_date(target_report_month: Any) -> date:
    """Converts 'YYYY-MM' or 'YYYY-MM-DD' safely to date(YYYY, MM, 1)."""
    val_str = str(target_report_month).strip()[:7]  # Take 'YYYY-MM'
    parts = val_str.split("-")
    return date(int(parts[0]), int(parts[1]), 1)

# ==============================================================================
# 3. BENCHMARK RATE RECONSTRUCTION (LOCKED V1 TRAIN/SERVE)
# ==============================================================================

import time
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from api.models.models import Project, ProjectUpdate

# In-memory storage for the global completed projects table
# Caches the table for 1 hour (3600 seconds) so new completed projects eventually sync
_COMPLETED_PROJECTS_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "ttl_seconds": 3600,
    "records": [],
    "global_prior_rate": 0.0
}


def get_cached_completed_history(db: Session, cost_threshold: float = 0.20) -> Tuple[List[Dict[str, Any]], float]:
    """
    Builds and caches the completed projects summary table in RAM.
    Avoids running a full-table join across Project and ProjectUpdate on every request.
    """
    current_time = time.time()

    # Return from memory if cache is still valid
    if _COMPLETED_PROJECTS_CACHE["records"] and (
            current_time - _COMPLETED_PROJECTS_CACHE["timestamp"] < _COMPLETED_PROJECTS_CACHE["ttl_seconds"]):
        return _COMPLETED_PROJECTS_CACHE["records"], _COMPLETED_PROJECTS_CACHE["global_prior_rate"]

    # 1. Fetch projects and their historical updates once
    all_projects = db.query(Project).all()
    project_map = {p.project_id: p for p in all_projects}

    updates = db.query(ProjectUpdate).order_by(ProjectUpdate.report_month.asc()).all()
    project_snapshots: Dict[str, List[ProjectUpdate]] = {}
    for u in updates:
        project_snapshots.setdefault(u.project_id, []).append(u)

    completed_history = []
    for pid, p in project_map.items():
        if pid not in project_snapshots or not p.original_cost_crore or float(p.original_cost_crore) <= 0:
            continue

        last_u = project_snapshots[pid][-1]

        is_completed = False
        comp_date = None
        if last_u.milestones_achieved and last_u.milestones_total and last_u.milestones_achieved >= last_u.milestones_total:
            is_completed = True
            comp_date = to_date(last_u.anticipated_commissioning_date) or to_date(last_u.revised_commissioning_date)
        elif last_u.anticipated_commissioning_date:
            comp_date = to_date(last_u.anticipated_commissioning_date)

        if is_completed and comp_date:
            final_cost = float(last_u.anticipated_cost_crore or last_u.revised_cost_crore or p.original_cost_crore)
            org_cost = float(p.original_cost_crore)
            # Replicating locked v1 20% overrun threshold
            had_overrun = 1 if ((final_cost - org_cost) / org_cost) >= cost_threshold else 0

            completed_history.append({
                "project_id": pid,
                "agency": p.implementing_agency,
                "sector": p.sector,
                "completion_date": comp_date,
                "had_overrun": had_overrun
            })

    # Global prior rate across historical completed projects
    global_prior = float(np.mean([r["had_overrun"] for r in completed_history])) if completed_history else 0.0

    # Store into in-memory cache
    _COMPLETED_PROJECTS_CACHE["records"] = completed_history
    _COMPLETED_PROJECTS_CACHE["global_prior_rate"] = global_prior
    _COMPLETED_PROJECTS_CACHE["timestamp"] = current_time

    return completed_history, global_prior


def calculate_v1_benchmarks(
    target_agency: Optional[str],
    target_sector: Optional[str],
    target_date: date,
    current_project_id: str,
    db: Session,
    alpha: float = 5.0,
    cost_threshold: float = 0.20
) -> Dict[str, float]:
    global _BENCHMARK_DF
    target_month_str = target_date.strftime("%Y-%m")

    # 1. Direct match from authoritative precomputed training benchmarks
    if _BENCHMARK_DF is not None:
        # Match against either YYYY-MM or YYYY-MM-DD (prefix match on first 7 chars)
        match = _BENCHMARK_DF[
            (_BENCHMARK_DF["project_id"].astype(str).str.strip() == str(current_project_id).strip()) &
            (_BENCHMARK_DF["report_month"].astype(str).str.slice(0, 7) == target_date.strftime("%Y-%m"))
            ]
        if not match.empty:
            return {
                "agency_overrun_rate": float(match["agency_overrun_rate"].iloc[0]),
                "agency_project_count_as_of_T": float(match["agency_project_count_as_of_T"].iloc[0]),
                "sector_overrun_rate": float(match["sector_overrun_rate"].iloc[0]),
            }

    # 2. Dynamic in-memory fallback for newly added live projects
    completed_history, global_prior_rate = get_cached_completed_history(db, cost_threshold)
    if not completed_history:
        return {
            "agency_overrun_rate": 0.0,
            "agency_project_count_as_of_T": 0.0,
            "sector_overrun_rate": 0.0
        }

    agency_prior_sum = sum(
        item["had_overrun"] for item in completed_history
        if item["project_id"] != current_project_id
        and item["completion_date"] < target_date
        and item["agency"] == target_agency
    )
    agency_prior_count = sum(
        1 for item in completed_history
        if item["project_id"] != current_project_id
        and item["completion_date"] < target_date
        and item["agency"] == target_agency
    )
    sector_prior_sum = sum(
        item["had_overrun"] for item in completed_history
        if item["project_id"] != current_project_id
        and item["completion_date"] < target_date
        and item["sector"] == target_sector
    )
    sector_prior_count = sum(
        1 for item in completed_history
        if item["project_id"] != current_project_id
        and item["completion_date"] < target_date
        and item["sector"] == target_sector
    )

    return {
        "agency_overrun_rate": float((agency_prior_sum + alpha * global_prior_rate) / (agency_prior_count + alpha)),
        "agency_project_count_as_of_T": float(agency_prior_count),
        "sector_overrun_rate": float((sector_prior_sum + alpha * global_prior_rate) / (sector_prior_count + alpha))
    }



# ==============================================================================
# 4. LOOKBACK HELPER (3M / 6M / 12M DATE LOOKUPS)
# ==============================================================================
def find_lookback_snapshot(
    updates_by_month: Dict[date, ProjectUpdate],
    current_date: date,
    months_ago: int,
    tolerance_months: int = 0
) -> Optional[ProjectUpdate]:
    # Exact calendar-month lookup. Missing historical snapshots remain missing.
    month_index = current_date.year * 12 + (current_date.month - 1) - months_ago
    target_year, month_zero = divmod(month_index, 12)
    target_date = date(target_year, month_zero + 1, 1)
    return updates_by_month.get(target_date)


# ==============================================================================
# 5. CORE FEATURE BUILDER (RAW SNAPSHOT -> 47 FEATURES)
# ==============================================================================
def build_feature_snapshot(
    project_id: str,
    target_report_month: str,
    db: Session
) -> pd.DataFrame:
    """
    Extract raw project/update data as of target_report_month,
    reconstruct the locked 47 ML features, and return a
    one-row DataFrame aligned to FEATURE_COLUMNS.

    This supports both:
    1. Existing government projects with historical snapshots.
    2. Newly added projects with only one snapshot and optional
       fields stored as NULL.
    """

    # ==========================================================
    # 1. FIND PROJECT
    # ==========================================================

    clean_project_id = str(project_id).strip()

    project = (
        db.query(Project)
        .filter(
            Project.project_id == clean_project_id
        )
        .first()
    )

    if not project:
        raise ValueError(
            f"Project '{clean_project_id}' not found in database."
        )

    # ==========================================================
    # 2. TARGET REPORT MONTH
    # ==========================================================

    current_report_date = get_target_report_month_date(
        target_report_month
    )

    target_month_str = current_report_date.strftime("%Y-%m")

    # ==========================================================
    # 3. GET ALL SNAPSHOTS UP TO T
    # ==========================================================

    updates = (
        db.query(ProjectUpdate)
        .filter(
            ProjectUpdate.project_id == clean_project_id,
            ProjectUpdate.report_month <= target_month_str
        )
        .order_by(
            ProjectUpdate.report_month.asc()
        )
        .all()
    )

    if not updates:
        raise ValueError(
            f"No snapshot history available for project "
            f"'{clean_project_id}' as of {target_month_str}."
        )

    latest_update = updates[-1]

    updates_by_month: Dict[date, ProjectUpdate] = {
        get_target_report_month_date(u.report_month): u
        for u in updates
    }

    # ==========================================================
    # 4. DATE FIELDS
    # ==========================================================

    approval_d = to_date(
        project.date_of_approval
    )

    org_comm_d = to_date(
        project.original_commissioning_date
    )

    rev_comm_d = to_date(
        latest_update.revised_commissioning_date
    )

    anti_comm_d = to_date(
        latest_update.anticipated_commissioning_date
    )

    # ==========================================================
    # 5. FINANCIAL FIELDS
    # ==========================================================

    org_cost = (
        float(project.original_cost_crore)
        if project.original_cost_crore is not None
        else np.nan
    )

    rev_cost = (
        float(latest_update.revised_cost_crore)
        if latest_update.revised_cost_crore is not None
        else np.nan
    )

    anti_cost = (
        float(latest_update.anticipated_cost_crore)
        if latest_update.anticipated_cost_crore is not None
        else np.nan
    )

    cum_exp = (
        float(
            latest_update.cumulative_expenditure_crore
        )
        if latest_update.cumulative_expenditure_crore is not None
        else np.nan
    )

    # Current cost = revised cost when available,
    # otherwise original cost.
    current_cost = (
        rev_cost
        if not np.isnan(rev_cost)
        else org_cost
    )

    # ==========================================================
    # 6. CALENDAR / STATIC FEATURES
    # ==========================================================

    month = current_report_date.month
    year = current_report_date.year

    sector = project.sector
    state = project.state

    approval_year = (
        approval_d.year
        if approval_d
        else np.nan
    )

    # Project age
    if approval_d:
        project_age = months_between(
            current_report_date,
            approval_d
        )

        if project_age is not None and project_age < 0:
            project_age = np.nan
    else:
        project_age = np.nan

    # Original planned duration
    if org_comm_d and approval_d:
        org_duration = months_between(
            org_comm_d,
            approval_d
        )

        if (
            org_duration is not None
            and org_duration <= 0
        ):
            org_duration = np.nan
    else:
        org_duration = np.nan

    # Duration overrun
    if (
        project_age is not None
        and org_duration is not None
        and not np.isnan(project_age)
        and not np.isnan(org_duration)
    ):
        duration_overrun_months = max(
            0.0,
            float(project_age - org_duration)
        )
    else:
        duration_overrun_months = np.nan

    # Remaining original duration
    if org_comm_d and current_report_date:
        diff_rem = months_between(
            org_comm_d,
            current_report_date
        )

        remaining_org_months = (
            float(diff_rem)
            if diff_rem is not None
            else np.nan
        )
    else:
        remaining_org_months = np.nan

    # ==========================================================
    # 7. SCHEDULE FEATURES
    # ==========================================================

    # Preferred source:
    # commissioning-date arithmetic.
    anticipated_delay_from_original = months_between(
        anti_comm_d,
        org_comm_d
    )

    # For newly added projects, commissioning dates may be
    # optional. If the user manually entered the original delay,
    # use that value as a fallback.
    if (
        anticipated_delay_from_original is None
        and latest_update.delay_original_months is not None
    ):
        anticipated_delay_from_original = float(
            latest_update.delay_original_months
        )

    # Remaining original months
    if org_comm_d:
        remaining_org_months = months_between(
            org_comm_d,
            current_report_date
        )

    # Difference between anticipated and revised
    # commissioning dates.
    delay_revised_months = months_between(
        anti_comm_d,
        rev_comm_d
    )

    # If both commissioning dates are unavailable,
    # preserve missingness rather than inventing a value.
    if (
        delay_revised_months is None
        and latest_update.delay_revised_months is not None
        and rev_comm_d is not None
        and anti_comm_d is None
    ):
        delay_revised_months = float(
            latest_update.delay_revised_months
        )

    # Model contract contains this intentionally misspelled
    # feature name.
    #
    # It represents:
    # revised commissioning date - current report month
    delay_revisied_months = months_between(
        rev_comm_d,
        current_report_date
    )

    # ==========================================================
    # 8. MILESTONE FEATURES
    # ==========================================================

    milestones_achieved = (
        latest_update.milestones_achieved
    )

    milestones_total = (
        latest_update.milestones_total
    )

    milestone_data_reliable = bool(
        milestones_total is not None
        and milestones_total > 0
    )

    if (
        milestone_data_reliable
        and milestones_achieved is not None
    ):
        milestone_completion_percentage = (
            float(milestones_achieved)
            / float(milestones_total)
        ) * 100.0
    else:
        milestone_completion_percentage = np.nan

    # ==========================================================
    # 9. SINGLE-SNAPSHOT COST / EXPENDITURE RATIOS
    # ==========================================================

    cost_revision_percentage = (
        (
            (rev_cost - org_cost)
            / org_cost
            * 100.0
        )
        if (
            not np.isnan(rev_cost)
            and not np.isnan(org_cost)
            and org_cost > 0
        )
        else np.nan
    )

    anticipated_cost_percentage = (
        (
            (anti_cost - org_cost)
            / org_cost
            * 100.0
        )
        if (
            not np.isnan(anti_cost)
            and not np.isnan(org_cost)
            and org_cost > 0
        )
        else np.nan
    )

    exp_vs_org_prct = (
        (
            cum_exp
            / org_cost
            * 100.0
        )
        if (
            not np.isnan(cum_exp)
            and not np.isnan(org_cost)
            and org_cost > 0
        )
        else np.nan
    )

    exp_vs_rev_prct = (
        (
            cum_exp
            / rev_cost
            * 100.0
        )
        if (
            not np.isnan(cum_exp)
            and not np.isnan(rev_cost)
            and rev_cost > 0
        )
        else np.nan
    )

    exp_vs_anti_prct = (
        (
            cum_exp
            / anti_cost
            * 100.0
        )
        if (
            not np.isnan(cum_exp)
            and not np.isnan(anti_cost)
            and anti_cost > 0
        )
        else np.nan
    )

    # ==========================================================
    # 10. PROJECT DURATION PROGRESS
    # ==========================================================

    project_duration_elapsed_percentage = (
        (
            project_age
            / org_duration
            * 100.0
        )
        if (
            project_age is not None
            and org_duration is not None
            and not np.isnan(project_age)
            and not np.isnan(org_duration)
            and org_duration > 0
        )
        else np.nan
    )

    # ==========================================================
    # 11. TREND / VELOCITY FEATURES
    # ==========================================================

    trend_metrics = {}

    for window in [3, 6, 12]:

        prior_snap = find_lookback_snapshot(
            updates_by_month,
            current_report_date,
            window
        )

        # ------------------------------------------------------
        # Cost growth
        # ------------------------------------------------------

        if (
            prior_snap
            and prior_snap.anticipated_cost_crore is not None
            and float(
                prior_snap.anticipated_cost_crore
            ) > 0
            and not np.isnan(anti_cost)
        ):
            prior_anti = float(
                prior_snap.anticipated_cost_crore
            )

            trend_metrics[
                f"cost_growth_{window}m"
            ] = (
                (anti_cost - prior_anti)
                / prior_anti
            ) * 100.0

        else:
            trend_metrics[
                f"cost_growth_{window}m"
            ] = np.nan

        # ------------------------------------------------------
        # Expenditure growth
        # ------------------------------------------------------

        if (
            prior_snap
            and prior_snap.cumulative_expenditure_crore is not None
            and float(
                prior_snap.cumulative_expenditure_crore
            ) > 0
            and not np.isnan(cum_exp)
        ):
            prior_exp = float(
                prior_snap.cumulative_expenditure_crore
            )

            trend_metrics[
                f"expenditure_growth_{window}m"
            ] = (
                (cum_exp - prior_exp)
                / prior_exp
            ) * 100.0

        else:
            trend_metrics[
                f"expenditure_growth_{window}m"
            ] = np.nan

        # ------------------------------------------------------
        # Schedule change
        # ------------------------------------------------------

        if prior_snap:

            p_anti = to_date(
                prior_snap.anticipated_commissioning_date
            )

            p_org = to_date(
                project.original_commissioning_date
            )

            prior_delay = months_between(
                p_anti,
                p_org
            )

            if (
                anticipated_delay_from_original is not None
                and prior_delay is not None
            ):
                trend_metrics[
                    f"schedule_change_{window}m"
                ] = float(
                    anticipated_delay_from_original
                    - prior_delay
                )
            else:
                trend_metrics[
                    f"schedule_change_{window}m"
                ] = np.nan

        else:
            trend_metrics[
                f"schedule_change_{window}m"
            ] = np.nan

        # ------------------------------------------------------
        # Milestone progress change
        # ------------------------------------------------------

        if (
            prior_snap
            and prior_snap.milestones_total is not None
            and prior_snap.milestones_total > 0
            and prior_snap.milestones_achieved is not None
        ):

            prior_ms_pct = (
                float(prior_snap.milestones_achieved)
                / float(prior_snap.milestones_total)
            ) * 100.0

            if not np.isnan(
                milestone_completion_percentage
            ):
                trend_metrics[
                    f"milestone_progress_change_{window}m"
                ] = float(
                    milestone_completion_percentage
                    - prior_ms_pct
                )
            else:
                trend_metrics[
                    f"milestone_progress_change_{window}m"
                ] = np.nan

        else:
            trend_metrics[
                f"milestone_progress_change_{window}m"
            ] = np.nan

    # ==========================================================
    # 12. MISMATCH / GAP SIGNALS
    # ==========================================================

    if not np.isnan(
        milestone_completion_percentage
    ):

        exp_gap_org = (
            exp_vs_org_prct
            - milestone_completion_percentage
            if not np.isnan(exp_vs_org_prct)
            else np.nan
        )

        exp_gap_anti = (
            exp_vs_anti_prct
            - milestone_completion_percentage
            if not np.isnan(exp_vs_anti_prct)
            else np.nan
        )

    else:
        exp_gap_org = np.nan
        exp_gap_anti = np.nan

    if (
        not np.isnan(exp_gap_org)
        and not np.isnan(exp_gap_anti)
    ):
        cost_rebaseline_signal = float(
            exp_gap_org - exp_gap_anti
        )
    else:
        cost_rebaseline_signal = np.nan

    if (
        not np.isnan(
            project_duration_elapsed_percentage
        )
        and not np.isnan(
            milestone_completion_percentage
        )
    ):
        schedule_progress_mismatch = float(
            project_duration_elapsed_percentage
            - milestone_completion_percentage
        )
    else:
        schedule_progress_mismatch = np.nan

    if (
        not np.isnan(
            project_duration_elapsed_percentage
        )
        and not np.isnan(
            schedule_progress_mismatch
        )
    ):
        early_phase_milestone_artifact = bool(
            (
                project_duration_elapsed_percentage
                <= 25.0
            )
            and (
                schedule_progress_mismatch
                < -20.0
            )
        )
    else:
        early_phase_milestone_artifact = False

    # ==========================================================
    # 13. HISTORICAL BENCHMARK FEATURES
    # ==========================================================

    benchmarks = calculate_v1_benchmarks(
        target_agency=project.implementing_agency,
        target_sector=project.sector,
        target_date=current_report_date,
        current_project_id=clean_project_id,
        db=db,
        alpha=5.0,
        cost_threshold=0.20
    )

    # ==========================================================
    # 14. ASSEMBLE EXACT 47 FEATURES
    # ==========================================================

    row_data = {

        "month": month,
        "year": year,

        "sector": sector,
        "state": state,
        "approval_year": approval_year,

        "project_age": project_age,
        "original_duration_months": org_duration,
        "duration_overrun_months": (
            duration_overrun_months
        ),

        "original_cost_crore": org_cost,
        "revised_cost_crore": rev_cost,
        "anticipated_cost_crore": anti_cost,
        "current_cost": current_cost,

        "cumulative_expenditure_crore": cum_exp,

        "anticipated_delay_from_original": (
            anticipated_delay_from_original
        ),

        "remaining_org_months": (
            remaining_org_months
        ),

        "delay_revised_months": (
            delay_revised_months
        ),

        # Keep exact spelling required by model artifact.
        "delay_revisied_months": (
            delay_revisied_months
        ),

        "milestones_achieved": (
            milestones_achieved
        ),

        "milestones_total": (
            milestones_total
        ),

        "milestone_completion_percentage": (
            milestone_completion_percentage
        ),

        "milestone_data_reliable": (
            milestone_data_reliable
        ),

        "cost_revision_percentage": (
            cost_revision_percentage
        ),

        "anticipated_cost_percentage": (
            anticipated_cost_percentage
        ),

        "exp_vs_anti_prct": (
            exp_vs_anti_prct
        ),

        "exp_vs_org_prct": (
            exp_vs_org_prct
        ),

        "exp_vs_rev_prct": (
            exp_vs_rev_prct
        ),

        "project_duration_elapsed_percentage": (
            project_duration_elapsed_percentage
        ),

        "cost_growth_3m": (
            trend_metrics["cost_growth_3m"]
        ),

        "cost_growth_6m": (
            trend_metrics["cost_growth_6m"]
        ),

        "cost_growth_12m": (
            trend_metrics["cost_growth_12m"]
        ),

        "expenditure_growth_3m": (
            trend_metrics["expenditure_growth_3m"]
        ),

        "expenditure_growth_6m": (
            trend_metrics["expenditure_growth_6m"]
        ),

        "expenditure_growth_12m": (
            trend_metrics["expenditure_growth_12m"]
        ),

        "schedule_change_3m": (
            trend_metrics["schedule_change_3m"]
        ),

        "schedule_change_6m": (
            trend_metrics["schedule_change_6m"]
        ),

        "schedule_change_12m": (
            trend_metrics["schedule_change_12m"]
        ),

        "milestone_progress_change_3m": (
            trend_metrics[
                "milestone_progress_change_3m"
            ]
        ),

        "milestone_progress_change_6m": (
            trend_metrics[
                "milestone_progress_change_6m"
            ]
        ),

        "milestone_progress_change_12m": (
            trend_metrics[
                "milestone_progress_change_12m"
            ]
        ),

        "expenditure_progress_gap_org": (
            exp_gap_org
        ),

        "expenditure_progress_gap_anti": (
            exp_gap_anti
        ),

        "cost_rebaseline_signal": (
            cost_rebaseline_signal
        ),

        "schedule_progress_mismatch": (
            schedule_progress_mismatch
        ),

        "early_phase_milestone_artifact": (
            early_phase_milestone_artifact
        ),

        "agency_overrun_rate": (
            benchmarks["agency_overrun_rate"]
        ),

        "agency_project_count_as_of_T": (
            benchmarks[
                "agency_project_count_as_of_T"
            ]
        ),

        "sector_overrun_rate": (
            benchmarks["sector_overrun_rate"]
        ),
    }

    # ==========================================================
    # 15. ALIGN EXACTLY TO MODEL FEATURE ORDER
    # ==========================================================

    df = pd.DataFrame([row_data])

    missing_features = [
        feature
        for feature in FEATURE_COLUMNS
        if feature not in df.columns
    ]

    if missing_features:
        raise ValueError(
            "Feature engineering failed. "
            f"Missing features: {missing_features}"
        )

    # Do not add/remove/reorder features manually.
    # The joblib artifact remains authoritative.
    df = df[FEATURE_COLUMNS]

    return df