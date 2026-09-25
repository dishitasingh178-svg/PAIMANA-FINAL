from datetime import datetime
import pytest
from api.models.models import Alert, Prediction, Project, ProjectUpdate
from api.services.alert_priority import (
    calculate_priority_score, calculate_data_confidence, classify_alert,
    financial_exposure, percentile95, effective_status, transition_status,
    actionable_alerts,
)
from api.services.alert_engine import CandidateAlert, _save_alert_if_new, generate_alerts


def populate(db):
    project = Project(project_id="p1", project_name="Test project", original_cost_crore=1000)
    db.add(project)
    db.flush()
    for i, month in enumerate(("2024-03", "2024-04", "2024-05")):
        db.add(ProjectUpdate(project_id="p1", report_month=month, anticipated_cost_crore=1200, cumulative_expenditure_crore=500+i*100, milestones_achieved=30, milestones_total=100))
        db.add(Prediction(project_id="p1", report_month=month, cost_risk_probability=.8, schedule_risk_probability=.7, cox_risk=.6, cox_risk_probability=.6, composite_risk_score=(40,54,78)[i], risk_tier="CRITICAL", generated_at=datetime(2024,6-i,1)))
    db.add_all([Alert(project_id="p1", alert_type="ML_RISK_WARNING", severity="CRITICAL", message="[2024-05] Model warning"), Alert(project_id="p1", alert_type="EXPENDITURE_PROGRESS_GAP", severity="WATCH", message="[2024-05] Progress gap")])
    db.commit()
    return project


@pytest.mark.parametrize("previous,current,expected", [(50,45,0),(50,50,0),(50,55,25),(50,60,50),(50,65,75),(50,70,100),(50,80,100),(None,78,0)])
def test_deterioration(previous, current, expected):
    result = calculate_priority_score(current, previous, None, None, "WATCH")
    assert result["priority_components"]["deterioration"] == expected
    assert result["risk_delta"] == (current-previous if previous is not None else None)


@pytest.mark.parametrize("severity,urgency", [("CRITICAL",100),("ELEVATED",70),("WATCH",40),(None,0),("other",0)])
def test_urgency(severity, urgency):
    assert calculate_priority_score(0,None,None,None,severity)["priority_score"] == urgency*.15


def test_priority_and_missing_cost():
    assert calculate_priority_score(78,54,1200,1200,"CRITICAL")["priority_score"] == 91.2
    assert calculate_priority_score(78,54,1200,1200,"CRITICAL")["priority_label"] == "IMMEDIATE"
    assert calculate_priority_score(None,None,None,None,None)["priority_score"] == 0
    assert calculate_priority_score(300,-100,10000,1,"CRITICAL")["priority_score"] == 100
    p = Project(original_cost_crore=100)
    u = ProjectUpdate(anticipated_cost_crore=300,revised_cost_crore=200)
    assert financial_exposure(p,u) == 300
    u.anticipated_cost_crore = None
    assert financial_exposure(p,u) == 200
    assert percentile95([None,100,200]) == 195


@pytest.mark.parametrize("kind,category", [("ML_RISK_WARNING","PREDICTIVE"),("RISK_DETERIORATION","DETERIORATION"),("EXPENDITURE_ACCELERATION","DETERIORATION"),("EXPENDITURE_PROGRESS_GAP","DETERIORATION"),("MILESTONE_STAGNATION","DETERIORATION"),("COST_ESCALATION","OBSERVED_ISSUE"),("SCHEDULE_SLIPPAGE","OBSERVED_ISSUE")])
def test_classification(kind, category):
    assert classify_alert(kind)[0] == category


@pytest.mark.parametrize("month,expected", [("2024-05","HIGH"),("2024-04","MEDIUM"),("2024-02","LOW")])
def test_confidence_freshness(month, expected):
    p = Project(original_cost_crore=100)
    u = ProjectUpdate(report_month=month,milestones_achieved=0,milestones_total=10,cumulative_expenditure_crore=30)
    pred = Prediction(report_month=month)
    assert calculate_data_confidence(p,u,pred,"2024-05","EXPENDITURE_PROGRESS_GAP")[0] == expected
    u.milestones_total = None
    assert calculate_data_confidence(p,u,pred,"2024-05","EXPENDITURE_PROGRESS_GAP")[0] == "LOW"
    assert calculate_data_confidence(p,None,pred,"2024-05","ML_RISK_WARNING")[0] == "LOW"


def test_workflow_and_legacy():
    a = Alert(is_resolved=False)
    assert effective_status(a) == "NEW"
    for status in ("ACKNOWLEDGED","UNDER_REVIEW","RESOLVED","DISMISSED","NEW"):
        transition_status(a,status,"Review note")
        assert a.status == status
        assert a.is_resolved == (status == "RESOLVED")
    assert all([a.acknowledged_at,a.resolved_at,a.dismissed_at,a.status_updated_at])
    a.is_resolved = True
    assert effective_status(a) == "RESOLVED"
    with pytest.raises(ValueError):
        transition_status(a,"BAD")


def test_api_history_priority_and_workflow(db, client):
    populate(db)
    items = client.get('/api/v1/alerts').json()
    assert items[0]['risk_score'] == 78
    assert items[0]['previous_risk_score'] == 54
    assert items[0]['risk_delta'] == 24
    priority = client.get('/api/v1/alerts/priority').json()
    assert len(priority) == 1 and priority[0]['active_alert_count'] == 2
    assert priority[0]['priority_score'] == 91.2
    assert client.get('/api/v1/alerts?alert_class=PREDICTIVE').json()[0]['alert_type'] == 'ML_RISK_WARNING'
    aid = items[0]['alert_id']
    for status in ('ACKNOWLEDGED','UNDER_REVIEW','RESOLVED'):
        response = client.patch(f'/api/v1/alerts/{aid}/status',json={'status':status,'review_note':'<script>literal note</script>'})
        assert response.status_code == 200
        assert response.json()['status'] == status
        db.expire_all()
        assert db.get(Alert,aid).is_resolved == (status == 'RESOLVED')
    assert len(client.get('/api/v1/alerts').json()) == 1
    assert len(client.get('/api/v1/alerts?status=RESOLVED').json()) == 1
    remaining = client.get('/api/v1/alerts').json()[0]['alert_id']
    assert client.patch(f'/api/v1/alerts/{remaining}/status',json={'status':'DISMISSED'}).status_code == 200
    assert client.get('/api/v1/alerts/priority').json() == []
    assert client.get('/api/v1/alerts/summary').json()['resolved'] == 1
    assert client.patch(f'/api/v1/alerts/{aid}/status',json={'status':'INVALID'}).status_code == 422
    assert client.patch('/api/v1/alerts/999/status',json={'status':'NEW'}).status_code == 404


def test_empty_and_missing_data(db, client):
    for endpoint in ('','/priority'):
        assert client.get('/api/v1/alerts'+endpoint).json() == []
    db.add(Project(project_id='empty',project_name='Missing data'))
    db.flush()
    db.add(Alert(project_id='empty',alert_type='ML_RISK_WARNING',severity='WATCH',message='Legacy'))
    db.commit()
    item = client.get('/api/v1/alerts').json()[0]
    assert item['financial_exposure_crore'] is None
    assert item['previous_risk_score'] is None
    assert item['data_confidence'] == 'LOW'


def test_dedup_and_escalation(db):
    p = populate(db)
    old = db.query(Alert).filter(Alert.alert_type == 'EXPENDITURE_PROGRESS_GAP').one()
    transition_status(old,'DISMISSED','Preserved note')
    assert _save_alert_if_new(db,'p1',CandidateAlert(old.alert_type,'WATCH','[2024-06] changed message')) is None
    assert old.status == 'DISMISSED'
    _save_alert_if_new(db,'p1',CandidateAlert(old.alert_type,'ELEVATED','[2024-06] escalation'))
    assert old.status == 'NEW' and old.review_note == 'Preserved note'
    assert old.severity == 'ELEVATED'
    candidate = CandidateAlert('COST_ESCALATION','WATCH','First')
    assert _save_alert_if_new(db,'p1',candidate) is not None
    assert _save_alert_if_new(db,'p1',candidate) is None
    generate_alerts(db,p,'2024-05',{'composite_risk_score':78,'risk_tier':'CRITICAL'})
    db.flush()
    count = db.query(Alert).count()
    generate_alerts(db,p,'2024-05',{'composite_risk_score':78,'risk_tier':'CRITICAL'})
    db.flush()
    assert db.query(Alert).count() == count


def test_same_month_reruns_are_not_previous_month(db):
    populate(db)
    db.add(Prediction(project_id='p1',report_month='2024-05',cost_risk_probability=.8,schedule_risk_probability=.8,cox_risk=.5,cox_risk_probability=.5,composite_risk_score=80,risk_tier='CRITICAL',generated_at=datetime(2025,1,1)))
    db.commit()
    item = actionable_alerts(db)[0]
    assert item['risk_score'] == 80 and item['previous_risk_score'] == 54


def test_filters_pagination_and_status_precedence(db, client):
    populate(db)
    assert len(client.get('/api/v1/alerts?limit=1&offset=1').json()) == 1
    assert client.get('/api/v1/alerts?project_id=missing').json() == []
    assert client.get('/api/v1/alerts?min_priority=99').json() == []
    alerts = db.query(Alert).order_by(Alert.alert_id).all()
    transition_status(alerts[0], 'UNDER_REVIEW')
    transition_status(alerts[1], 'ACKNOWLEDGED')
    db.commit()
    assert client.get('/api/v1/alerts/priority').json()[0]['status'] == 'UNDER_REVIEW'
    transition_status(alerts[0], 'RESOLVED')
    db.commit()
    item = client.get('/api/v1/alerts/priority').json()[0]
    assert item['highest_alert_severity'] == 'WATCH'
    assert item['priority_score'] == 82.2
    assert item['status'] == 'ACKNOWLEDGED'


def test_no_cross_project_history_and_constant_query_count(db):
    from sqlalchemy import event
    populate(db)
    db.add(Project(project_id='p2', project_name='No prediction history'))
    db.flush()
    db.add(Alert(project_id='p2', alert_type='ML_RISK_WARNING', severity='WATCH', message='Warning'))
    db.commit()
    queries = []
    def capture(*args):
        queries.append(args[2])
    event.listen(db.bind, 'before_cursor_execute', capture)
    try:
        items = actionable_alerts(db)
    finally:
        event.remove(db.bind, 'before_cursor_execute', capture)
    assert len(queries) == 4
    item = next(a for a in items if a['project_id'] == 'p2')
    assert item['previous_risk_score'] is None


def test_missing_core_financial_metrics_lower_confidence():
    p = Project(original_cost_crore=100)
    u = ProjectUpdate(report_month='2024-05', milestones_achieved=1, milestones_total=10)
    pred = Prediction(report_month='2024-05')
    assert calculate_data_confidence(p,u,pred,'2024-05','EXPENDITURE_PROGRESS_GAP')[0] == 'LOW'


def test_resolved_condition_can_generate_new_alert(db):
    populate(db)
    alert = db.query(Alert).filter(Alert.alert_type == 'ML_RISK_WARNING').one()
    transition_status(alert,'RESOLVED')
    db.flush()
    new = _save_alert_if_new(db,'p1',CandidateAlert('ML_RISK_WARNING','CRITICAL','New period'))
    assert new is not None and new.alert_id != alert.alert_id
