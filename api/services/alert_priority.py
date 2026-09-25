"""Deterministic operational triage above the unchanged prediction pipeline."""
from collections import defaultdict
from datetime import datetime, timezone
import math
import re

from sqlalchemy import func
from sqlalchemy.orm import aliased

from api.models.models import Alert, Prediction, Project, ProjectUpdate
from api.services.alert_engine import _get_cost_baseline

STATUSES = {"NEW", "ACKNOWLEDGED", "UNDER_REVIEW", "RESOLVED", "DISMISSED"}
CLOSED = {"RESOLVED", "DISMISSED"}
URGENCY = {"CRITICAL": 100, "ELEVATED": 70, "WATCH": 40}
CLASSES = {
    "ML_RISK_WARNING": "PREDICTIVE",
    "RISK_DETERIORATION": "DETERIORATION",
    "EXPENDITURE_ACCELERATION": "DETERIORATION",
    "EXPENDITURE_PROGRESS_GAP": "DETERIORATION",
    "MILESTONE_STAGNATION": "DETERIORATION",
    "COST_ESCALATION": "OBSERVED_ISSUE",
    "SCHEDULE_SLIPPAGE": "OBSERVED_ISSUE",
}
LABELS = {"PREDICTIVE": "Predictive Risk", "DETERIORATION": "Deteriorating", "OBSERVED_ISSUE": "Observed Issue"}
GUIDANCE = {
    "ML_RISK_WARNING": ("Predictive models indicate elevated cost or schedule risk; an adverse outcome is not certain.", "Future cost growth or commissioning delays may require intervention.", "Review recent project trends and the model evidence before intervention."),
    "RISK_DETERIORATION": ("Composite risk increased by at least 10 points between reporting periods.", "A worsening risk trajectory may increase delivery exposure.", "Verify which project conditions changed since the previous reporting period."),
    "COST_ESCALATION": ("Anticipated cost grew at least 8%, or revised cost exceeds original cost by at least 10%.", "Reported cost growth may increase the funding requirement.", "Review documented scope changes, approvals and re-baselining supporting the increase."),
    "EXPENDITURE_ACCELERATION": ("Latest spending growth is at least 1.5 times the recent positive-growth average and at least 1% of the rule cost baseline.", "Accelerating expenditure may increase funding requirements ahead of delivery.", "Confirm whether increased expenditure corresponds to planned execution, procurement or milestone completion."),
    "EXPENDITURE_PROGRESS_GAP": ("Expenditure as a share of the rule cost baseline exceeds milestone completion by at least 15 percentage points.", "Financial expenditure may be advancing ahead of physical delivery.", "Confirm whether the gap reflects legitimate procurement/payment timing, delayed reporting or execution underperformance."),
    "MILESTONE_STAGNATION": ("No milestone advancement was reported across at least four periods while expenditure reached at least 20% of the rule cost baseline.", "Stalled reported progress may put the delivery schedule at risk.", "Verify whether physical progress stalled or milestone reporting is delayed with the implementing agency."),
    "SCHEDULE_SLIPPAGE": ("Reported delay reached at least 3 months, increased by at least 1 month, or the commissioning date moved at least 30 days.", "Reported delay may defer commissioning and project benefits.", "Review delayed activities and confirm whether the current commissioning target remains achievable."),
}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def clamp(value):
    return min(100.0, max(0.0, value))


def effective_status(alert):
    return "RESOLVED" if alert.is_resolved else (alert.status or "NEW")


def transition_status(alert, status, note=None):
    if status not in STATUSES:
        raise ValueError("Invalid alert status")
    now = datetime.now(timezone.utc)
    if effective_status(alert) != status:
        alert.status_updated_at = now
        field = {"ACKNOWLEDGED": "acknowledged_at", "RESOLVED": "resolved_at", "DISMISSED": "dismissed_at"}.get(status)
        if field:
            setattr(alert, field, now)
    elif note is not None and note != alert.review_note:
        alert.status_updated_at = now
    alert.status = status
    alert.is_resolved = status == "RESOLVED"
    if note is not None:
        alert.review_note = note


def classify_alert(alert_type):
    category = CLASSES.get(alert_type, "OBSERVED_ISSUE")
    return category, LABELS[category]


def financial_exposure(project, update):
    for value in (getattr(update, "anticipated_cost_crore", None), getattr(update, "revised_cost_crore", None), project.original_cost_crore):
        value = number(value)
        if value is not None and value > 0:
            return value
    return None


def percentile95(values):
    values = sorted(v for v in values if v is not None and v > 0)
    if not values:
        return None
    index = (len(values) - 1) * .95
    low = math.floor(index)
    high = math.ceil(index)
    return values[low] + (values[high] - values[low]) * (index - low)


def calculate_priority_score(current, previous, exposure, p95, severity):
    current, previous = number(current), number(previous)
    delta = round(current - previous, 2) if current is not None and previous is not None else None
    components = {
        "risk": clamp(current or 0),
        "deterioration": clamp((delta or 0) * 5),
        "financial_exposure": clamp(exposure / p95 * 100) if exposure is not None and p95 and p95 > 0 else 0,
        "alert_urgency": URGENCY.get(severity, 0),
    }
    score = round(clamp(sum(components[key] * weight for key, weight in zip(components, (.40, .25, .20, .15)))), 1)
    label = "IMMEDIATE" if score >= 80 else "HIGH" if score >= 65 else "MEDIUM" if score >= 45 else "ROUTINE"
    return {"priority_score": score, "priority_label": label, "risk_delta": delta,
            "previous_risk_score": previous, "historical_comparison_available": delta is not None,
            "priority_components": components}


def month_index(month):
    try:
        date = datetime.strptime(month, "%Y-%m")
        return date.year * 12 + date.month
    except (ValueError, TypeError):
        return None


def calculate_data_confidence(project, update, prediction, portfolio_month, alert_type):
    if update is None:
        return "LOW", ["No usable project update is available."]
    reasons, level = [], 0
    current, latest = month_index(update.report_month), month_index(portfolio_month)
    if current is None or latest is None:
        reasons.append("Reporting freshness could not be established.")
        level = 2
    else:
        lag = max(0, latest - current)
        reasons.append("Latest project update matches portfolio reporting month." if lag == 0 else f"Project update is {lag} reporting cycles behind the portfolio.")
        level = 0 if lag == 0 else 1 if lag == 1 else 2
    missing = []
    if financial_exposure(project, update) is None:
        missing.append("Meaningful financial values are unavailable.")
        if alert_type in {"COST_ESCALATION", "EXPENDITURE_ACCELERATION", "EXPENDITURE_PROGRESS_GAP", "MILESTONE_STAGNATION"}:
            level = 2
    if alert_type in {"MILESTONE_STAGNATION", "EXPENDITURE_PROGRESS_GAP"}:
        achieved, total = number(update.milestones_achieved), number(update.milestones_total)
        if achieved is None or total is None or total <= 0 or not 0 <= achieved <= total:
            missing.append("Milestone fields are incomplete or invalid.")
            level = 2
    if alert_type in {"EXPENDITURE_ACCELERATION", "EXPENDITURE_PROGRESS_GAP", "MILESTONE_STAGNATION"} and number(update.cumulative_expenditure_crore) is None:
        missing.append("Expenditure is unavailable.")
        level = 2
    if alert_type == "COST_ESCALATION" and not any(number(v) is not None and number(v) > 0 for v in (update.anticipated_cost_crore, update.revised_cost_crore)):
        missing.append("Reported anticipated and revised costs are unavailable.")
        level = 2
    if alert_type == "SCHEDULE_SLIPPAGE" and all(getattr(update, f) is None for f in ("delay_revised_months", "delay_original_months", "revised_commissioning_date", "anticipated_commissioning_date")):
        missing.append("Schedule evidence is unavailable.")
        level = 2
    if prediction is None:
        missing.append("Model prediction is unavailable.")
        if alert_type in {"ML_RISK_WARNING", "RISK_DETERIORATION"}:
            level = 2
    elif prediction.report_month != update.report_month:
        missing.append("Model prediction and latest project update cover different reporting months.")
        prediction_month = month_index(prediction.report_month)
        if prediction_month is None or (latest is not None and latest - prediction_month >= 2):
            level = 2
    if missing:
        level = max(level, 2 if len(missing) > 1 else 1)
    return ("HIGH", "MEDIUM", "LOW")[level], reasons + missing


def recent_rows(db, model, id_column, limit):
    # Deduplicate prediction reruns per month before selecting recent distinct months.
    revision_order = (model.generated_at.desc().nullslast(), id_column.desc()) if model is Prediction else (id_column.desc(),)
    ranked = db.query(model, func.row_number().over(partition_by=(model.project_id, model.report_month), order_by=revision_order).label("revision")).subquery()
    row = aliased(model, ranked)
    months = db.query(row, func.row_number().over(partition_by=row.project_id, order_by=row.report_month.desc()).label("period")).filter(ranked.c.revision == 1).subquery()
    return db.query(aliased(model, months)).filter(months.c.period <= limit).order_by(months.c.report_month.desc()).all()


class TriageContext:
    """Four bounded/batched queries; no per-project lazy loads."""
    def __init__(self, db):
        self.projects = {p.project_id: p for p in db.query(Project).all()}
        self.updates = defaultdict(list)
        self.predictions = defaultdict(list)
        for row in recent_rows(db, ProjectUpdate, ProjectUpdate.id, 8):
            self.updates[row.project_id].append(row)
        for row in recent_rows(db, Prediction, Prediction.prediction_id, 2):
            self.predictions[row.project_id].append(row)
        self.portfolio_month = max((rows[0].report_month for rows in self.updates.values()), default=None)
        self.exposures = {pid: financial_exposure(p, next(iter(self.updates[pid]), None)) for pid, p in self.projects.items()}
        self.p95 = percentile95(self.exposures.values())

    def serialize(self, alert, severity=None):
        project = self.projects[alert.project_id]
        updates, predictions = self.updates[alert.project_id], self.predictions[alert.project_id]
        update = updates[0] if updates else None
        prior_update = updates[1] if len(updates) > 1 else None
        prediction = predictions[0] if predictions else None
        previous = predictions[1] if len(predictions) > 1 else None
        score = number(prediction.composite_risk_score) if prediction else None
        priority = calculate_priority_score(score, previous.composite_risk_score if previous else None, self.exposures[alert.project_id], self.p95, severity or alert.severity)
        category, label = classify_alert(alert.alert_type)
        confidence, reasons = calculate_data_confidence(project, update, prediction, self.portfolio_month, alert.alert_type)
        if alert.alert_type == "RISK_DETERIORATION" and previous is None:
            confidence = "LOW"
            reasons.append("Previous reporting period unavailable.")
        why, consequence, investigation = GUIDANCE.get(alert.alert_type, ("Review the recorded alert condition.", "Delivery exposure requires review.", "Verify the recorded evidence with the implementing agency."))
        evidence = []

        def add(label, current, previous=None, unit=None, current_month=None, previous_month=None):
            if current is None:
                return
            change = round(current - previous, 2) if isinstance(current, (float, int)) and isinstance(previous, (float, int)) else None
            evidence.append(dict(label=label, current=current, previous=previous, change=change, unit=unit, current_report_month=current_month, previous_report_month=previous_month))

        add("Composite risk", score, number(previous.composite_risk_score) if previous else None, "points", prediction.report_month if prediction else None, previous.report_month if previous else None)
        for field, title in (("cost_risk_probability", "Cost risk model"), ("schedule_risk_probability", "Schedule risk model"), ("cox_risk_probability", "Lifecycle risk model")):
            value = number(getattr(prediction, field, None))
            add(title, round(value * 100, 2) if value is not None else None, unit="%", current_month=prediction.report_month if prediction else None)
        if update:
            for field, title, unit in (("anticipated_cost_crore", "Anticipated cost", "crore"), ("revised_cost_crore", "Revised cost", "crore"), ("cumulative_expenditure_crore", "Cumulative expenditure", "crore"), ("delay_revised_months", "Revised delay", "months"), ("delay_original_months", "Original delay", "months")):
                add(title, number(getattr(update, field)), number(getattr(prior_update, field, None)), unit, update.report_month, prior_update.report_month if prior_update else None)
            def milestones(row):
                return f"{row.milestones_achieved} / {row.milestones_total}" if row and row.milestones_achieved is not None and row.milestones_total and row.milestones_total > 0 else None
            add("Milestones achieved", milestones(update), milestones(prior_update), current_month=update.report_month, previous_month=prior_update.report_month if prior_update else None)
            for field in ("revised_commissioning_date", "anticipated_commissioning_date"):
                value, old = getattr(update, field), getattr(prior_update, field, None)
                add(field.replace("_", " ").title(), value.isoformat() if value else None, old.isoformat() if old else None, current_month=update.report_month, previous_month=prior_update.report_month if prior_update else None)
            baseline = _get_cost_baseline(project, update)
            if alert.alert_type in {"EXPENDITURE_PROGRESS_GAP", "EXPENDITURE_ACCELERATION", "MILESTONE_STAGNATION"}:
                add("Rule cost baseline (revised, anticipated, original)", baseline, unit="crore", current_month=update.report_month)
            if alert.alert_type == "EXPENDITURE_PROGRESS_GAP" and baseline and update.cumulative_expenditure_crore is not None and update.milestones_achieved is not None and update.milestones_total and update.milestones_total > 0:
                gap = float(update.cumulative_expenditure_crore) / baseline * 100 - update.milestones_achieved / update.milestones_total * 100
                add("Expenditure minus milestone progress", round(gap, 2), unit="percentage points", current_month=update.report_month)
            if alert.alert_type in {"MILESTONE_STAGNATION", "EXPENDITURE_ACCELERATION"}:
                for row in reversed(updates[:6]):
                    if alert.alert_type == "MILESTONE_STAGNATION":
                        add("Milestone history", milestones(row), current_month=row.report_month)
                    else:
                        add("Expenditure history", number(row.cumulative_expenditure_crore), unit="crore", current_month=row.report_month)
                required = 4 if alert.alert_type == "MILESTONE_STAGNATION" else 5
                if len(updates) < required:
                    confidence = "LOW"
                    reasons.append("Insufficient reporting history to verify the trajectory warning.")
        add("Original approved cost", number(project.original_cost_crore), unit="crore")
        match = re.match(r"\[(\d{4}-\d{2})\]", alert.message or "")
        changed = alert.message
        if priority["risk_delta"] is not None and priority["risk_delta"] >= 10:
            changed += f" Latest model comparison: risk increased {priority['risk_delta']:g} points ({previous.report_month} to {prediction.report_month})."
        result = dict(alert_id=alert.alert_id, project_id=alert.project_id.strip(), project_name=project.project_name, sector=project.sector or "Infrastructure", implementing_agency=project.implementing_agency, state=project.state,
                      issue_summary=alert.message, message=alert.message, trigger_reason=alert.alert_type, alert_type=alert.alert_type,
                      severity=alert.severity, status=effective_status(alert), is_resolved=bool(alert.is_resolved), review_note=alert.review_note,
                      risk_score=score, composite_risk_score=score, risk_tier=prediction.risk_tier if prediction else "UNASSESSED",
                      financial_exposure_crore=self.exposures[alert.project_id], portfolio_p95_exposure_crore=self.p95,
                      alert_class=category, alert_class_label=label, data_confidence=confidence, data_confidence_reasons=reasons,
                      what_changed=changed, why_flagged=why, potential_consequence=consequence, recommended_investigation=investigation,
                      evidence=evidence, report_month=update.report_month if update else None, prediction_report_month=prediction.report_month if prediction else None,
                      previous_prediction_report_month=previous.report_month if previous else None, alert_report_month=match.group(1) if match else None, portfolio_report_month=self.portfolio_month, **priority)
        for field in ("cost_risk_probability", "schedule_risk_probability", "cox_risk_probability"):
            result[field] = number(getattr(prediction, field, None))
        for field in ("triggered_at", "status_updated_at", "acknowledged_at", "resolved_at", "dismissed_at"):
            value = getattr(alert, field)
            result[field] = value.isoformat() if value else None
        return result


def actionable_alerts(db):
    context = TriageContext(db)
    items = [context.serialize(a) for a in db.query(Alert).all() if a.project_id in context.projects]
    return sorted(items, key=lambda a: (a["status"] not in CLOSED, a["priority_score"], a["triggered_at"] or "", a["alert_id"]), reverse=True)


def priority_projects(items):
    grouped = defaultdict(list)
    for item in items:
        if item["status"] not in CLOSED:
            grouped[item["project_id"]].append(item)
    result = []
    for alerts in grouped.values():
        dominant = max(alerts, key=lambda a: (URGENCY.get(a["severity"], 0), a["risk_delta"] or 0, a["triggered_at"] or "", a["alert_id"]))
        item = dict(dominant)
        item.update(highest_alert_severity=dominant["severity"], active_alert_count=len(alerts), dominant_alert_type=dominant["alert_type"],
                    status=next(s for s in ("NEW", "UNDER_REVIEW", "ACKNOWLEDGED") if any(a["status"] == s for a in alerts)),
                    attention_reason=(f"Risk increased {dominant['risk_delta']:g} points; " if dominant["risk_delta"] is not None and dominant["risk_delta"] > 0 else "") + f"{len(alerts)} active warning(s), led by {dominant['alert_type'].replace('_', ' ').lower()}.")
        item["data_confidence"] = min((a["data_confidence"] for a in alerts), key=lambda c: ("LOW", "MEDIUM", "HIGH").index(c))
        item["data_confidence_reasons"] = list(dict.fromkeys(r for a in alerts for r in a["data_confidence_reasons"]))
        result.append(item)
    return sorted(result, key=lambda a: (-a["priority_score"], a["project_id"]))
