"""Regression coverage for PDF metadata corruption, using only isolated test DBs."""
from unittest.mock import Mock

import fitz
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.models.models import Project, ProjectUpdate, Prediction
from api.services.pdf_extractor import parse_block, extract_pdf
from api.services.project_ingestion import ingest_project_records
from api.services.state_names import canonical_state
from api.routers import analytics, dashboard
from database import get_db


def block(pid='N18000047', metadata='NTPC, BIHAR', inline=False):
    lines = [f'BARH STPP', f'STAGE II [{pid}]', metadata, '02/2008',
             '7,341.04', '-', '8,000.00', '100.00', '03/2014', '-', '03/2015', '-', '0/0']
    return [' '.join(lines)] if inline else lines


@pytest.mark.parametrize('inline', [False, True])
def test_parser_bounds_metadata_before_dates_and_financial_commas(inline):
    row = parse_block(block(inline=inline), 1, 'POWER', '2014-09', 'September2014.pdf', 1)
    assert row['state'] == 'BIHAR'
    assert row['implementing_agency'] == 'NTPC'
    assert row['project_name'] == 'BARH STPP STAGE II'
    assert row['original_cost_crore'] == 7341.04
    assert row['anticipated_cost_crore'] == 8000
    assert row['revised_cost_crore'] is None
    assert row['milestones_achieved'] == row['milestones_total'] == 0


@pytest.mark.parametrize('metadata,agency,state', [
    (', BIHAR', '', 'BIHAR'), ('BIHAR', '', 'BIHAR'), ('NTPC,', 'NTPC', ''),
    ('NTPC', 'NTPC', ''), ('', '', ''), ('NTPC, TAMIL\nNADU', 'NTPC', 'TAMIL NADU'),
])
def test_missing_and_wrapped_metadata(metadata, agency, state):
    row = parse_block(block(metadata=metadata), 1, 'POWER', '2014-09', 'x.pdf', 1)
    assert (row['implementing_agency'], row['state']) == (agency, state)


@pytest.mark.parametrize('value,expected', [
    (' bihar ', 'BIHAR'), ('tamil  nadu', 'TAMIL NADU'), ('A & N ISLANDS', 'ANDAMAN AND NICOBAR ISLANDS'),
    ('D & N HAVELI', 'DADRA AND NAGAR HAVELI'), ('Pondicherry', 'PUDUCHERRY'),
    ('Chhatisgarh', 'CHHATTISGARH'), ('Orissa', 'ODISHA'), ('Uttaranchal', 'UTTARAKHAND'),
    ('NCT of Delhi', 'DELHI'), ('Jammu & Kashmir', 'JAMMU AND KASHMIR'), ('Ladakh', 'LADAKH'),
    ('MULTI STATE', 'MULTI STATE'), ('ANDHRA PRADESH .', 'ANDHRA PRADESH'),
    ('BIHAR 02/2008 7', None), ('BIHAR 0/0', None), ('BIHAR $$$', None), ('Atlantis', None),
])
def test_strict_state_names(value, expected):
    assert canonical_state(value) == expected


def record(pid, **overrides):
    return dict(project_id=pid, project_name='A project', report_month='2014-09',
                original_cost_crore=100, anticipated_cost_crore=120, **overrides)


def test_safe_ingestion_preserves_upserts_and_reports_invalid_fields(db):
    db.add(Project(project_id='N18000047', project_name='Existing', state='BIHAR', sector='POWER', implementing_agency='NTPC'))
    db.commit()
    before = db.query(Project).count()
    result = ingest_project_records(db, [
        record('N18000047', state='BIHAR 02/2008 7', implementing_agency='NTPC 02/2008 7', sector='POWER 02/2008 7'),
        record('N18000048', state=' tamil  nadu '),
        record('N18000048', state='TAMIL NADU'),
        record('N18000049', state='BIHAR 0/0'),
        dict(record('N18000050'), project_name='BROKEN 02/2008 7 0/0'),
    ])
    db.commit()
    assert before == 1 and db.query(Project).count() == 3
    assert result['projects_created'] == 2 and result['projects_updated'] == 2
    assert result['updates_created'] == 3 and result['updates_updated'] == 1
    assert len(result['errors']) == 1 and len(result['warnings']) == 4
    assert db.query(ProjectUpdate).count() == 3
    existing = db.get(Project, 'N18000047')
    assert (existing.state, existing.implementing_agency, existing.sector) == ('BIHAR', 'NTPC', 'POWER')
    assert db.get(Project, 'N18000049').state is None
    assert result['affected_pairs'] == [(f'N1800004{i}', '2014-09') for i in (7, 8, 9)]
    correction = ingest_project_records(db, [record('N18000047', state='Orissa', implementing_agency='NEW AGENCY')])
    assert existing.state == 'ODISHA' and existing.implementing_agency == 'NEW AGENCY'
    assert correction['updates_updated'] == 1 and not correction['warnings']
    assert db.query(ProjectUpdate).count() == 3


def test_invalid_name_preserved_for_existing_project(db):
    db.add(Project(project_id='N18000047', project_name='Good name', state='BIHAR'))
    db.commit()
    result = ingest_project_records(db, [dict(record('N18000047'), project_name='BROKEN 02/2008 7 0/0')])
    assert db.get(Project, 'N18000047').project_name == 'Good name'
    assert result['warnings'][0]['field'] == 'project_name'
    assert result['affected_pairs']


def test_analytics_and_map_do_not_infer_contaminated_states(db):
    for i, state in enumerate(['BIHAR', ' bihar ', 'BIHAR 02/2008 7', 'BIHAR 0/0', None, 'Orissa', 'MULTI STATE']):
        pid = str(i)
        db.add(Project(project_id=pid, project_name=pid, state=state, original_cost_crore=100))
        db.add(Prediction(project_id=pid, report_month='2014-09', cost_risk_probability=.8,
                         schedule_risk_probability=.8, cox_risk=1, cox_risk_probability=.8,
                         composite_risk_score=80, risk_tier='CRITICAL'))
    db.commit()
    rows = {r['state']: r for r in analytics.get_state_summary(db)['data']}
    assert rows['BIHAR']['projects'] == 2
    assert rows['UNRECOGNIZED']['projects'] == 2
    assert rows[None]['projects'] == 1
    assert sum(r['projects'] for r in rows.values()) == 7
    states = {r['state']: r for r in analytics.get_state_analytics(db)['data']}
    assert states['BIHAR']['projects'] == 2 and states['UNRECOGNIZED']['projects'] == 2
    app = FastAPI()
    app.include_router(dashboard.router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.get('/api/v1/dashboard/ongoing-high-risk')
    assert response.status_code == 200
    pins = response.json()
    assert {p['project_id'] for p in pins} == {'0', '1', '5'}
    assert all((p['lat'], p['lng']) != dashboard.STATE_COORDINATES['CENTRAL'] for p in pins)


def make_pdf(path):
    # Actual text-layer PDF fixture covering both supported row-start layouts.
    doc = fitz.open()
    page = doc.new_page()
    lines = ['(September 2014)', 'Si.No Project Date of Approval Cumulative Anticipated Milestones', 'POWER']
    lines += ['1'] + block() + ['2 NEW PROJECT [N18000048]'] + block('N18000048', 'NTPC, ODISHA')[2:]
    page.insert_text((40, 40), '\n'.join(lines), fontsize=10)
    doc.save(path)
    doc.close()


def test_pdf_upload_existing_and_new_ids_reach_real_predictions(db, tmp_path, monkeypatch):
    from api.routers import projects
    from api.services import pdf_pipeline, prediction_service
    db.add(Project(project_id='N18000047', project_name='Existing', state='BIHAR', original_cost_crore=100))
    db.commit()
    pdf = tmp_path / 'September2014.pdf'
    make_pdf(pdf)
    rows, pages, errors = extract_pdf(pdf)
    assert len(rows) == 2 and pages == [0] and not errors
    assert [r['state'] for r in rows] == ['BIHAR', 'ODISHA']
    # Keep the real parser, ingestion, feature engineering, model and alert path.
    # Route all sessions to this isolated DB; execute the background worker inline.
    class SessionProxy:
        def __getattr__(self, name):
            return getattr(db, name)
        def close(self):
            pass
    monkeypatch.setattr(pdf_pipeline, 'SessionLocal', SessionProxy)
    monkeypatch.setattr(prediction_service, 'SessionLocal', SessionProxy)
    reporter = Mock()
    monkeypatch.setattr(projects, 'submit_job', lambda job_id, fn, *args: fn(reporter, *args))
    monkeypatch.setattr(projects, '_pdf_last_upload_at', 0)
    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        with pdf.open('rb') as stream:
            response = client.post('/api/v1/projects/upload-pdf', files={'file': (pdf.name, stream, 'application/pdf')})
        assert response.status_code == 202
        assert not reporter.failed.called, reporter.failed.call_args
        result = reporter.completed.call_args.args[0]
        assert (result['projects_created'], result['projects_updated'], result['updates_created']) == (1, 1, 2)
        assert result['predictions_generated'] == 2 and result['predictions_failed'] == 0
        assert db.query(Project).count() == 2 and db.query(ProjectUpdate).count() == 2
        assert db.query(Prediction).count() == 2
        assert client.get('/api/v1/projects').status_code == 200
        assert client.get('/api/v1/projects/N18000047').json()['state'] == 'BIHAR'
        # Idempotent re-upload: existing project/month rows and predictions update.
        monkeypatch.setattr(projects, '_pdf_last_upload_at', 0)
        with pdf.open('rb') as stream:
            repeated = client.post('/api/v1/projects/upload-pdf', files={'file': (pdf.name, stream, 'application/pdf')})
        assert repeated.status_code == 202
        again = reporter.completed.call_args.args[0]
        assert (again['projects_created'], again['projects_updated'], again['updates_created'], again['updates_updated']) == (0, 2, 0, 2)
        assert again['predictions_generated'] == 2
        assert db.query(Project).count() == db.query(ProjectUpdate).count() == db.query(Prediction).count() == 2
    print('ISOLATED PDF: projects 1 -> 2; new 1; existing updated 1; snapshots 2; predictions 2; alerts', result['alerts_created'])
    print('RE-UPLOAD: new 0; existing updated 2; snapshots updated 2; predictions 2; duplicate projects 0')


def test_manual_ingestion_reports_invalid_optional_metadata(db):
    from api.routers import projects
    app = FastAPI()
    app.include_router(projects.router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.post('/api/v1/projects', json={'project_id':'manual-1', 'project_name':'Manual', 'state':'BIHAR 0/0'})
    assert response.status_code == 201
    assert response.json()['warnings'][0]['field'] == 'state'
    assert db.get(Project, 'manual-1').state is None


def test_existing_pages_and_read_endpoints_load_with_malformed_state(db):
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from api.routers import projects, alerts
    db.add(Project(project_id='page-test', project_name='Page test', state='BIHAR 02/2008 7', original_cost_crore=100))
    db.commit()
    app = FastAPI()  # No production startup hooks or migrations.
    for router in (projects.router, dashboard.router, analytics.router, alerts.router):
        app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.mount('/', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'frontend', html=True))
    with TestClient(app) as client:
        for page in ('dashboard', 'projects', 'project-details', 'risk-analytics', 'early-warnings', 'add-project'):
            response = client.get('/' + page + '.html')
            assert response.status_code == 200 and '<html' in response.text
        for endpoint in ('dashboard/summary', 'dashboard/ongoing-high-risk', 'dashboard/risk-distribution',
                         'dashboard/sector-breakdown', 'analytics/states', 'analytics/state-summary',
                         'analytics/sectors', 'analytics/trends', 'projects', 'projects/page-test',
                         'alerts/workspace', 'alerts/summary'):
            assert client.get('/api/v1/' + endpoint).status_code == 200, endpoint


def april_cases():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).parent / 'fixtures/april_2024_metadata.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', april_cases(), ids=lambda c: c['expected']['project_id'])
def test_user_supplied_april_pdf_golden_metadata(case):
    # Text-layer blocks from the supplied April 2024 report. Numeric/date
    # expectations also match the pre-fix parser; only state is corrected.
    parsed = parse_block(case['block'], case['serial'], case['sector'], case['report_month'],
                         case['source_file'], case['source_page'])
    assert parsed == case['expected']
    assert canonical_state(parsed['state']) is not None


def test_april_pdf_records_ingest_and_score_in_isolation(db, monkeypatch):
    from api.services import pdf_pipeline, prediction_service
    from api.models.models import Alert
    rows = [parse_block(c['block'], c['serial'], c['sector'], c['report_month'], c['source_file'], c['source_page']) for c in april_cases()]
    db.add(Project(project_id=rows[0]['project_id'], project_name='Existing', state='BIHAR'))
    db.commit()
    result = ingest_project_records(db, rows)
    db.commit()
    assert (result['projects_created'], result['projects_updated'], result['updates_created']) == (17, 1, 18)
    assert not result['errors'] and not result['warnings']
    assert db.query(Project).count() == db.query(ProjectUpdate).count() == 18
    class SessionProxy:
        def __getattr__(self, name):
            return getattr(db, name)
        def close(self):
            pass
    monkeypatch.setattr(prediction_service, 'SessionLocal', SessionProxy)
    reporter = Mock()
    scores = pdf_pipeline._predict(reporter, result['affected_pairs'])
    assert scores['succeeded'] == 18 and scores['failed'] == 0
    assert db.query(Prediction).count() == 18
    assert db.query(Alert).count() == scores['alerts_created']
    print('APRIL PDF: projects 1 -> 18; new 17; existing updated 1; snapshots 18; flagged/rejected 0; predictions 18; alerts', scores['alerts_created'])
