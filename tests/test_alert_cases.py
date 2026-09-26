import pytest
from sqlalchemy import text
from api.models.models import Alert, Project
from api.services.alert_engine import CandidateAlert, _save_alert_if_new, generate_alerts
from api.services.alert_cases import get_cases, update_project_case
from test_alert_triage import populate


def three_signals(db):
    project = populate(db)
    db.add(Alert(project_id='p1', alert_type='SCHEDULE_SLIPPAGE', severity='ELEVATED', message='Reported delay'))
    db.commit()
    return project


def test_unique_counts_and_multi_classification(db, client):
    three_signals(db)
    summary = client.get('/api/v1/alerts/summary').json()
    assert summary['raw_alert_count'] == 3
    assert summary['new'] == summary['total_cases'] == summary['total_projects'] == 1
    cases = client.get('/api/v1/alerts/cases?status=NEW').json()
    assert len(cases) == 1 and len(cases[0]['underlying_signals']) == 3
    assert set(cases[0]['alert_classifications']) == {'PREDICTIVE','DETERIORATION','OBSERVED_ISSUE'}
    for classification in cases[0]['alert_classifications']:
        assert len(client.get('/api/v1/alerts/cases?classification='+classification).json()) == (classification == cases[0]['dominant_classification'])


def test_case_transitions_notes_and_refetch(db, client):
    three_signals(db)
    previous = 'NEW'
    for status in ['ACKNOWLEDGED','UNDER_REVIEW','RESOLVED','NEW','DISMISSED']:
        note = f'{status}: <script>literal officer note</script>'
        result = client.patch('/api/v1/alerts/projects/p1/status',json={'status':status,'review_note':note})
        assert result.status_code == 200
        assert result.json()['workflow_status'] == status and result.json()['review_note'] == note
        assert client.get('/api/v1/alerts/cases?status='+previous).json() == []
        refetched = client.get('/api/v1/alerts/cases?status='+status).json()
        assert len(refetched) == 1 and refetched[0]['review_note'] == note
        db.expire_all()
        assert all(a.status == status and a.review_note == note and a.is_resolved == (status == 'RESOLVED') for a in db.query(Alert).all())
        counts = client.get('/api/v1/alerts/summary').json()
        assert counts[status.lower()] == 1
        assert sum(counts[s] for s in ['new','acknowledged','under_review','resolved','dismissed']) == 1
        if status in ['RESOLVED','DISMISSED']:
            assert client.get('/api/v1/alerts/priority').json() == []
        previous = status


def test_new_evidence_preserves_review(db):
    project = three_signals(db)
    update_project_case(db,'p1','ACKNOWLEDGED','Agency contacted')
    _save_alert_if_new(db,'p1',CandidateAlert('EXPENDITURE_PROGRESS_GAP','CRITICAL','Escalated evidence'))
    db.commit()
    case = get_cases(db)[0]
    assert case['workflow_status'] == 'ACKNOWLEDGED' and case['has_new_evidence']
    assert case['review_note'] == 'Agency contacted'
    _save_alert_if_new(db,'p1',CandidateAlert('EXPENDITURE_ACCELERATION','WATCH','Genuinely new signal'))
    db.commit()
    assert all(a.status == 'ACKNOWLEDGED' for a in db.query(Alert).all())
    update_project_case(db,'p1','UNDER_REVIEW','Reviewing new evidence')
    assert not get_cases(db)[0]['has_new_evidence']
    for _ in range(2):
        generate_alerts(db,project,'2024-05',{'composite_risk_score':78,'risk_tier':'CRITICAL'})
        db.commit()
    assert len(get_cases(db)) == 1 and get_cases(db)[0]['workflow_status'] == 'UNDER_REVIEW'
    assert db.query(Alert).count() == 3 + 1 + 1  # original 3 + new signal + risk deterioration


def test_legacy_nulls_duplicate_signals_and_empty(db, client):
    assert client.get('/api/v1/alerts/cases').json() == []
    db.add(Project(project_id='legacy',project_name='Legacy'))
    db.flush()
    db.add_all([Alert(project_id='legacy',alert_type='UNKNOWN',severity='WATCH',message='Legacy') for _ in range(3)])
    db.commit()
    # Empty status behaves like null for a legacy installation before backfill.
    db.execute(text("UPDATE alerts SET status = ''"))
    db.commit()
    case = client.get('/api/v1/alerts/cases?status=NEW').json()[0]
    assert case['risk_score'] is None and case['financial_exposure_crore'] is None
    assert case['workflow_status'] == 'NEW' and case['signal_count'] == 3
    assert client.get('/api/v1/alerts/summary').json()['new'] == 1


def test_project_transition_errors(db, client):
    assert client.patch('/api/v1/alerts/projects/missing/status',json={'status':'ACKNOWLEDGED'}).status_code == 404
    assert client.patch('/api/v1/alerts/projects/missing/status',json={'status':'BAD'}).status_code == 422


def test_closed_unchanged_rerun_does_not_reopen(db):
    three_signals(db)
    update_project_case(db,'p1','RESOLVED','Closed')
    before = db.query(Alert).count()
    assert _save_alert_if_new(db,'p1',CandidateAlert('SCHEDULE_SLIPPAGE','ELEVATED','Reported delay')) is None
    db.commit()
    assert db.query(Alert).count() == before and get_cases(db)[0]['workflow_status'] == 'RESOLVED'


def test_dominant_tie_break_independent_of_row_order():
    from itertools import permutations
    from api.services.alert_cases import dominant_order
    signals = [dict(priority_score=80, alert_class=c, severity='ELEVATED', alert_id=i)
               for i, c in enumerate(['PREDICTIVE', 'DETERIORATION', 'OBSERVED_ISSUE'])]
    for ordering in permutations(signals):
        assert max(ordering, key=dominant_order)['alert_class'] == 'PREDICTIVE'
    signals[1]['priority_score'] = 81
    assert max(signals, key=dominant_order)['alert_class'] == 'DETERIORATION'


def test_workspace_single_aggregation_query_budget(db, client, monkeypatch):
    from sqlalchemy import event
    from api.services import alert_priority
    three_signals(db)
    original = alert_priority.percentile95
    percentiles = []
    monkeypatch.setattr(alert_priority, 'percentile95', lambda values: (percentiles.append(1), original(values))[1])
    statements = []
    def count(*args): statements.append(args[2])
    event.listen(db.bind, 'before_cursor_execute', count)
    try:
        response = client.get('/api/v1/alerts/workspace?status=NEW&limit=1')
        assert response.status_code == 200
        body = response.json()
        assert len(body['cases']) == body['summary']['new'] == 1
        assert body['has_more'] is False
        assert 'underlying_signals' in body['cases'][0]
        assert 'underlying_signals' not in body['priority'][0]
        assert len(statements) == 6 and len(percentiles) == 1
    finally:
        event.remove(db.bind, 'before_cursor_execute', count)


def test_dominant_groups_are_disjoint(db, client):
    for i, kind in enumerate(['ML_RISK_WARNING', 'MILESTONE_STAGNATION', 'COST_ESCALATION']):
        db.add(Project(project_id=str(i), project_name=kind))
        db.flush()
        db.add(Alert(project_id=str(i), alert_type=kind, severity='WATCH', message='Recorded signal'))
    db.commit()
    groups = [{c['project_id'] for c in client.get('/api/v1/alerts/cases?classification='+category).json()}
              for category in ['PREDICTIVE','DETERIORATION','OBSERVED_ISSUE']]
    assert groups == [{'0'}, {'1'}, {'2'}]
