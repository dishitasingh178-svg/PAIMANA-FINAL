"""One operational case per project, retaining raw alerts as contributing signals."""
from collections import defaultdict
from datetime import datetime, timezone

from api.models.models import Alert, Project
from api.services.alert_priority import CLOSED, URGENCY, actionable_alerts, effective_status, transition_status


def case_status(signals):
    opened = [s for s in signals if s["status"] not in CLOSED]
    if opened:
        reviewed = [s for s in opened if s["status"] in {"ACKNOWLEDGED", "UNDER_REVIEW"}]
        return max(reviewed, key=workflow_order)["status"] if reviewed else "NEW"
    return max(signals, key=workflow_order)["status"]


def workflow_order(signal):
    return (signal.get("status_updated_at") or "", signal.get("alert_id") or 0)


CLASS_RANK = {"PREDICTIVE": 3, "DETERIORATION": 2, "OBSERVED_ISSUE": 1}


def dominant_order(signal):
    # Priority first, then the documented class tie-break; IDs never choose a class.
    return (signal.get("priority_score") or 0, CLASS_RANK.get(signal.get("alert_class"), 0),
            URGENCY.get(signal.get("severity"), 0), signal.get("alert_type") or "", signal.get("alert_id") or 0)


def aggregate_cases(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item["project_id"]].append(item)
    cases = []
    for pid, signals in grouped.items():
        status = case_status(signals)
        opened = [s for s in signals if s["status"] not in CLOSED]
        relevant = opened or [s for s in signals if s["status"] == status]
        dominant = max(relevant, key=dominant_order)
        reviewed = [s for s in relevant if s["status"] == status]
        workflow = max(reviewed, key=workflow_order)
        note_source = max((s for s in relevant if s.get("review_note") is not None), key=workflow_order, default=workflow)
        item = dict(dominant)
        evidence = []
        seen = set()
        for signal in relevant:
            for entry in signal.get("evidence") or []:
                key = repr(sorted(entry.items()))
                if key not in seen:
                    seen.add(key)
                    evidence.append(entry)
        has_new_evidence = status in {"ACKNOWLEDGED", "UNDER_REVIEW"} and any(
            (s.get("evidence_updated_at") or "") > (workflow.get("status_updated_at") or "") for s in opened
        )
        item.update(
            project_id=pid, workflow_status=status, status=status,
            is_resolved=status == "RESOLVED", highest_severity=dominant.get("severity"),
            highest_alert_severity=dominant.get("severity"), active_signal_count=len(opened),
            active_alert_count=len(opened), signal_count=len(relevant),
            dominant_classification=dominant["alert_class"],
            contributing_classifications=sorted({s["alert_class"] for s in relevant}),
            underlying_signals=relevant, alert_classifications=sorted({s["alert_class"] for s in relevant}),
            review_note=note_source.get("review_note"), status_updated_at=workflow.get("status_updated_at"),
            has_new_evidence=has_new_evidence, evidence=evidence,
            dominant_alert_type=dominant.get("alert_type"),
            attention_reason=f"{len(relevant)} contributing signals. {dominant.get('what_changed') or 'Review the available evidence.'}",
            data_confidence=min((s.get("data_confidence", "LOW") for s in relevant), key=lambda c: {"LOW":0,"MEDIUM":1,"HIGH":2}.get(c,0)),
            data_confidence_reasons=list(dict.fromkeys(reason for s in relevant for reason in s.get("data_confidence_reasons", []))),
        )
        cases.append(item)
    return sorted(cases, key=lambda c: (-(c.get("priority_score") or 0), c["project_id"]))


def get_cases(db):
    return aggregate_cases(actionable_alerts(db))


def update_project_case(db, project_id, status, note):
    # Same parent lock as alert generation: new signals cannot slip into a transition.
    project = db.query(Project).filter(Project.project_id == project_id).with_for_update().first()
    if project is None:
        return None
    signals = db.query(Alert).filter(Alert.project_id == project_id).with_for_update().all()
    if not signals:
        return None
    opened = [a for a in signals if effective_status(a) not in CLOSED]
    # A closed case can be reopened; keep earlier, already-closed signals as history
    # when transitioning a currently open case.
    relevant = opened or signals
    now = datetime.now(timezone.utc)
    for alert in relevant:
        transition_status(alert, status, note)
        alert.status_updated_at = now
    db.commit()
    return next(c for c in get_cases(db) if c["project_id"] == project_id)
