import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import engine, get_session
from app.main import app
from app.models.access import AccessAuditEvent
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert
from app.models.knowledge import KnowledgeDocument, KnowledgePassage
from app.models.mental_health import MentalHealthCheckIn
from app.models.nutrition import FoodProduct, FoodStockMovement, MissionFoodLot
from app.models.predictive import PredictionModel, PredictionRun, RecommendationEvent, RecommendationFeedback, RiskPrediction
from app.models.preflight import Mission, MissionMember
from app.models.spacecraft import Spacecraft
from app.models.user import User
from app.services.mission_rag import RagSettings
from app.services.predictive.config import rules_config
from app.services.predictive.training import train_outcome_model
from app.services.predictive_service import PredictiveService
from tests.predictive_synthetic import fatigue_cohort
from tests.public_identity import public_headers


class FakeRag:
    settings = RagSettings(minimum_similarity=0.1)

    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def request(self, path, body=None):
        evidence = json.loads(body['prompt'])['evidence']
        return {'response': json.dumps({'summary': 'Documented sleep accommodation guidance supports reviewing rest periods.', 'citation_ids': [evidence[0]['id']]})}


class InventingRag(FakeRag):
    def request(self, path, body=None):
        return {'response': json.dumps({'summary': 'There is a 90% probability of collapse.', 'citation_ids': [123456]})}


class UnavailableRag(FakeRag):
    def embed(self, texts):
        raise ConnectionError('Ollama offline')


@pytest.fixture
def predictive_engine():
    if os.getenv('PREDICTIVE_POSTGRES_TESTS') != '1':
        pytest.skip('Requires isolated PostgreSQL schemas; set PREDICTIVE_POSTGRES_TESTS=1')
    schema = 'predictive_test_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    isolated = create_engine(engine.url, connect_args={'options': f'-csearch_path={schema}'})
    SQLModel.metadata.create_all(isolated)
    with engine.connect() as connection:
        definition = connection.execute(text("SELECT pg_get_functiondef('public.salus_cosine_similarity(double precision[], double precision[])'::regprocedure)")).scalar_one()
    with isolated.begin() as connection:
        connection.execute(text(definition.replace('public.salus_cosine_similarity', f'{schema}.salus_cosine_similarity')))
    try:
        yield isolated
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))


@pytest.fixture(autouse=True)
def no_manual_cooldown(monkeypatch):
    monkeypatch.setenv('PREDICTION_MANUAL_COOLDOWN_SECONDS', '0')


@pytest.fixture
def session(predictive_engine):
    with Session(predictive_engine) as session:
        yield session


@pytest.fixture
def client(session):
    def override():
        yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def user(session, name, **profiles):
    row = User(name=name, email=f'{name.lower().replace(" ", "-")}@example.test', hashed_password='!', **profiles)
    session.add(row)
    session.flush()
    return row


def observation(session, astronaut, recorder, mission, indicator, value, at, **extra):
    session.add(HealthObservation(astronaut_id=astronaut.id, mission_id=mission.id, indicator=indicator, value=value, collected_at=at,
                                  recorded_at=at + timedelta(minutes=5), source='self_report' if recorder.id == astronaut.id else 'manual_measurement',
                                  recorded_by_user_id=recorder.id, **extra))


def sleep_fatigue_history(session, astronaut, mission, now, deviated=True):
    for days_ago in range(40, 15, -1):
        at = now - timedelta(days=days_ago)
        observation(session, astronaut, astronaut, mission, 'sleep_duration', 450 + (days_ago % 3) * 5, at.replace(hour=7))
        observation(session, astronaut, astronaut, mission, 'fatigue', 3 + days_ago % 2, at.replace(hour=8))
    for days_ago in range(4, 0, -1):
        at = now - timedelta(days=days_ago)
        observation(session, astronaut, astronaut, mission, 'sleep_duration', 320 if deviated else 452, at.replace(hour=7))
        observation(session, astronaut, astronaut, mission, 'fatigue', 8 if deviated else 3, at.replace(hour=8))


@pytest.fixture
def crew(session):
    now = datetime.now(timezone.utc)
    vehicle = Spacecraft(name='Synthetic vehicle', status='in_use')
    session.add(vehicle)
    session.flush()
    mission = Mission(name='Synthetic predictive mission', status='in_progress', spacecraft_id=vehicle.id, crew_size=2,
                      planned_launch_at=now - timedelta(days=45), started_at=now - timedelta(days=45))
    people = {
        'astronaut': user(session, 'Astro One', is_astronaut=True), 'second': user(session, 'Astro Two', is_astronaut=True),
        'surgeon': user(session, 'Flight Surgeon', is_physician=True), 'psychologist': user(session, 'Mission Psychologist', is_psychologist=True),
        'nutritionist': user(session, 'Mission Nutritionist', is_nutritionist=True), 'admin': user(session, 'Mission Admin', is_mission_admin=True),
        'global': user(session, 'Global Admin', is_global_admin=True), 'outsider': user(session, 'Other Surgeon', is_physician=True),
    }
    session.add(mission)
    session.flush()
    roles = {'astronaut': 'astronaut', 'second': 'astronaut', 'surgeon': 'flight_surgeon', 'psychologist': 'psychologist', 'nutritionist': 'nutritionist', 'admin': 'mission_admin'}
    members = {}
    for key, role in roles.items():
        members[key] = MissionMember(mission_id=mission.id, user_id=people[key].id, role=role)
        session.add(members[key])
    session.flush()
    sleep_fatigue_history(session, people['astronaut'], mission, now)
    sleep_fatigue_history(session, people['second'], mission, now)
    for days_ago in range(40, 0, -1):
        day = (now - timedelta(days=days_ago))
        stress = 5 if days_ago <= 4 else 2 + days_ago % 2
        session.add(MentalHealthCheckIn(mission_id=mission.id, mission_member_id=members['astronaut'].id, check_in_date=day.date(), happiness_level=3, satisfaction_level=3,
                                        stress_level=stress, created_at=day.replace(hour=20), updated_at=day.replace(hour=20), updated_by_user_id=people['astronaut'].id))
    food = FoodProduct(name='Synthetic stew', category='food', preservation_method='thermostabilized', physical_form='solid', reference_quantity=100,
                       reference_unit='g', reference_basis='stored', preparation_method='ready_to_consume')
    session.add(food)
    session.flush()
    lot = MissionFoodLot(mission_id=mission.id, food_product_id=food.id, lot_code='LOT-1', expiration_date=now.date() + timedelta(days=2),
                         initial_quantity=1000, remaining_quantity=1000, stock_unit='g')
    session.add(lot)
    session.flush()
    session.add(FoodStockMovement(lot_id=lot.id, quantity=1000, stock_unit='g', movement_type='initial', purpose='receipt',
        recorded_by_user_id=people['admin'].id, recorded_at=now - timedelta(days=1),
        risk_snapshot={'reference_delta': '10', 'event_at': (now - timedelta(days=1)).isoformat(), 'food_name': food.name,
                       'expiration_date': lot.expiration_date.isoformat(), 'unit': 'g', 'quantity_per_reference': '100'}))
    session.commit()
    return SimpleCrew(mission, vehicle, people, members)


class SimpleCrew:
    def __init__(self, mission, vehicle, people, members):
        self.mission, self.vehicle, self.people, self.members = mission, vehicle, people, members

    def headers(self, session, key, profile=None):
        return public_headers(session, self.people[key].id, profile)


def predictions_of(view):
    return {row['risk_type']: row for row in view['latest']['predictions']}


def test_single_migration_head_includes_predictive_tables():
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ['5b3c4d5e6f72']
    assert script.get_revision('5b3c4d5e6f72').down_revision == '4a2b3c4d5e61'
    assert script.get_revision('4a2b3c4d5e61').down_revision == '3f1a2b4c5d60'
    assert script.get_revision('3f1a2b4c5d60').down_revision == '2d9e3f405162'


def test_physician_analysis_respects_domains_and_produces_recommendations(client, session, crew):
    astronaut = crew.people['astronaut'].id
    response = client.post(f'/v1/predictions/astronauts/{astronaut}/analyze?mission_id={crew.mission.id}', headers=crew.headers(session, 'surgeon'))
    assert response.status_code == 200, response.text
    view = response.json()
    found = predictions_of(view)
    assert {'sleep_deficit', 'sleep_fatigue_combined', 'fatigue_increase'} <= set(found)
    assert 'psychological' not in view['visible_domains']
    assert not any(row['domain'] == 'psychological' for row in view['latest']['predictions'])
    assert found['musculoskeletal_insufficient_data']['prediction_kind'] == 'insufficient_data'
    assert all(row['calibrated_probability'] is None and not row['probability_valid'] for row in view['latest']['predictions'])
    assert 'sleep_duration' in view['timeline'] and 'mental_stress' not in view['timeline']
    assert view['indicators']['sleep_duration']['baseline_source'] == 'individual_history'
    codes = {row['action']['code'] for row in view['recommendations']}
    assert {'rest_period_review', 'fatigue_monitoring'} <= codes
    assert all(row['status'] == 'pending' and row['rationale'] for row in view['recommendations'])
    assert session.exec(select(AccessAuditEvent).where(AccessAuditEvent.action == 'analyze_astronaut')).first() is not None


def test_psychological_predictions_are_limited_to_psychologist_and_astronaut(client, session, crew):
    astronaut = crew.people['astronaut'].id
    PredictiveService(session, crew.people['surgeon']).analyze_astronaut(astronaut, crew.mission.id)
    psychologist = client.get(f'/v1/predictions/astronauts/{astronaut}?mission_id={crew.mission.id}', headers=crew.headers(session, 'psychologist')).json()
    assert psychologist['visible_domains'] == ['psychological']
    assert 'psychological_stress_persistent' in predictions_of(psychologist)
    assert {row['domain'] for row in psychologist['latest']['predictions']} == {'psychological'}
    assert set(psychologist['timeline']) == {'mental_stress', 'mental_happiness', 'mental_satisfaction'}
    own = client.get(f'/v1/predictions/astronauts/{astronaut}', headers=crew.headers(session, 'astronaut')).json()
    assert {'psychological', 'sleep', 'cardiovascular'} <= {row['domain'] for row in own['latest']['predictions']}
    nutrition = client.get(f'/v1/predictions/astronauts/{astronaut}?mission_id={crew.mission.id}', headers=crew.headers(session, 'nutritionist')).json()
    assert {row['domain'] for row in nutrition['latest']['predictions']} == {'nutrition'}
    assert client.get(f'/v1/predictions/astronauts/{astronaut}?mission_id={crew.mission.id}', headers=crew.headers(session, 'outsider')).status_code == 403
    assert client.get(f'/v1/predictions/astronauts/{astronaut}?mission_id={crew.mission.id}', headers=crew.headers(session, 'admin')).status_code == 403
    assert client.get(f'/v1/predictions/astronauts/{crew.people["astronaut"].id}', headers=crew.headers(session, 'second')).status_code == 403


def test_analysis_is_idempotent_and_does_not_duplicate_recommendations(session, crew):
    service = PredictiveService(session, crew.people['surgeon'])
    first = service.analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    events = session.exec(select(RecommendationEvent)).all()
    second = service.analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    assert first.id == second.id
    assert len(session.exec(select(PredictionRun)).all()) == 1
    assert len(session.exec(select(RecommendationEvent)).all()) == len(events)
    observation(session, crew.people['astronaut'], crew.people['astronaut'], crew.mission, 'fatigue', 9, datetime.now(timezone.utc) - timedelta(minutes=30))
    session.commit()
    third = service.analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    assert third.id != first.id
    open_events = session.exec(select(RecommendationEvent).where(RecommendationEvent.status.in_(['pending', 'accepted']))).all()
    assert len(open_events) == len({(row.subject_id, row.action_id) for row in open_events})


def test_manual_analysis_rate_limit(client, session, crew, monkeypatch):
    monkeypatch.setenv('PREDICTION_MANUAL_COOLDOWN_SECONDS', '300')
    url = f'/v1/predictions/astronauts/{crew.people["astronaut"].id}/analyze?mission_id={crew.mission.id}'
    assert client.post(url, headers=crew.headers(session, 'surgeon')).status_code == 200
    limited = client.post(url, headers=crew.headers(session, 'surgeon'))
    assert limited.status_code == 429
    assert limited.headers['retry-after'] == '300'


def test_feedback_and_outcome_flow(client, session, crew):
    PredictiveService(session, crew.people['surgeon']).analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    listing = client.get('/v1/recommendations?status=pending', headers=crew.headers(session, 'surgeon')).json()
    target = next(row for row in listing if row['action']['code'] == 'fatigue_monitoring')
    url = f"/v1/recommendations/{target['id']}"
    assert client.get(url, headers=crew.headers(session, 'nutritionist')).status_code == 404
    assert client.post(url + '/feedback', json={'decision': 'accepted', 'justification': 'Plan reviewed'}, headers=crew.headers(session, 'admin')).status_code == 404
    assert client.post(url + '/feedback', json={'decision': 'executed', 'justification': 'Too early'}, headers=crew.headers(session, 'surgeon')).status_code == 422
    assert client.post(url + '/feedback', json={'decision': 'executed', 'justification': 'Skipped acceptance', 'executed_action': 'Daily reports'}, headers=crew.headers(session, 'surgeon')).status_code == 409
    accepted = client.post(url + '/feedback', json={'decision': 'accepted', 'justification': 'Daily self-reports are feasible'}, headers=crew.headers(session, 'surgeon'))
    assert accepted.status_code == 200 and accepted.json()['status'] == 'accepted'
    executed = client.post(url + '/feedback', json={'decision': 'executed', 'justification': 'Started', 'executed_action': 'Daily sleep and fatigue reports for 72 hours'}, headers=crew.headers(session, 'surgeon'))
    assert executed.json()['status'] == 'executed'
    outcome = client.post(url + '/outcomes', json={'indicator': 'fatigue', 'value_before': 8, 'value_after': 4, 'observation_window_hours': 72, 'result': 'improved'}, headers=crew.headers(session, 'surgeon'))
    assert outcome.status_code == 201
    body = outcome.json()
    assert [row['decision'] for row in body['feedback']] == ['accepted', 'executed']
    assert body['outcomes'][0]['result'] == 'improved'
    assert len(session.exec(select(RecommendationFeedback)).all()) == 2
    assert session.exec(select(AccessAuditEvent).where(AccessAuditEvent.action == 'outcome_recorded')).first() is not None


def test_rejection_requires_responsible_role(client, session, crew):
    PredictiveService(session, crew.people['surgeon']).analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    target = next(row for row in client.get('/v1/recommendations', headers=crew.headers(session, 'psychologist')).json() if row['action']['code'] == 'psychological_support_referral')
    assert target['can_decide'] is True
    response = client.post(f"/v1/recommendations/{target['id']}/feedback", json={'decision': 'rejected', 'justification': 'Spoke with the crew member yesterday'}, headers=crew.headers(session, 'psychologist'))
    assert response.json()['status'] == 'rejected'


def add_sleep_passage(session):
    document = KnowledgeDocument(title='NASA OCHMO-TB-041 Sleep Accommodations', source_url='https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-041-sleep-accommodations.pdf',
                                 revision='Rev B', is_public=True, indexing_status='completed', embedding_model=RagSettings().embedding_model, embedding_dimension=3)
    session.add(document)
    session.flush()
    session.add(KnowledgePassage(document_id=document.id, section='pdf:2:0', page_number=2, content='Sleep accommodations protect the sleep opportunity and reduce fatigue during rest schedule planning.',
                                 topic_codes=['sleep'], embedding=[1.0, 0.0, 0.0]))
    session.commit()


def pending_rest_review(session, crew):
    PredictiveService(session, crew.people['surgeon']).analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    session.commit()
    events = session.exec(select(RecommendationEvent)).all()
    return next(event for event in events if PredictiveService(session, crew.people['surgeon']).event_response(event)['action']['code'] == 'rest_period_review')


def test_rag_evidence_cites_real_passages(session, crew):
    add_sleep_passage(session)
    event = pending_rest_review(session, crew)
    PredictiveService(session, crew.people['surgeon'], rag=FakeRag()).fill_evidence(event)
    assert event.explanation['state'] == 'documented'
    assert event.explanation['generated'] is True
    assert event.sources[0]['title'].startswith('NASA OCHMO-TB-041')
    assert event.sources[0]['page'] == 2
    assert 'astronaut_id' not in event.explanation['data_sent_to_llm'] and 'name' not in event.explanation['data_sent_to_llm']


def test_rag_rejects_invented_citations_and_survives_ollama_failure(session, crew):
    add_sleep_passage(session)
    event = pending_rest_review(session, crew)
    PredictiveService(session, crew.people['surgeon'], rag=InventingRag()).fill_evidence(event)
    assert event.explanation['state'] == 'documented'
    assert event.explanation['generated'] is False
    assert event.explanation['generation_state'] == 'unavailable_or_rejected'
    assert '90%' not in event.explanation['summary']
    PredictiveService(session, crew.people['surgeon'], rag=UnavailableRag()).fill_evidence(event)
    assert event.explanation['state'] == 'rag_unavailable'
    assert event.sources == []
    assert event.status == 'pending'


def test_no_documentation_is_reported(session, crew):
    event = pending_rest_review(session, crew)
    PredictiveService(session, crew.people['surgeon'], rag=FakeRag()).fill_evidence(event)
    assert event.explanation['state'] == 'no_documentary_evidence'
    assert event.explanation['catalog_references']


def test_critical_clinical_alert_blocks_preventive_monitoring_and_is_preserved(session, crew):
    astronaut = crew.people['astronaut']
    now = datetime.now(timezone.utc)
    for days_ago in range(40, 15, -1):
        observation(session, astronaut, crew.people['surgeon'], crew.mission, 'heart_rate', 60 + days_ago % 2, (now - timedelta(days=days_ago)).replace(hour=9), activity='rest')
    for days_ago in range(4, 0, -1):
        observation(session, astronaut, crew.people['surgeon'], crew.mission, 'heart_rate', 78, (now - timedelta(days=days_ago)).replace(hour=9), activity='rest')
    session.flush()
    trigger = session.exec(select(HealthObservation).where(HealthObservation.indicator == 'heart_rate').order_by(HealthObservation.collected_at.desc())).first()
    alert = HealthAlert(astronaut_id=astronaut.id, mission_id=crew.mission.id, rule_id='heart_rate_critical', rule_version='v', profile_snapshot={}, indicator='heart_rate',
                        severity='critical', reason='Synthetic critical alert', trigger_observation_id=trigger.id)
    session.add(alert)
    session.commit()
    PredictiveService(session, crew.people['surgeon']).analyze_astronaut(astronaut.id, crew.mission.id)
    prediction = session.exec(select(RiskPrediction).where(RiskPrediction.risk_type == 'cardiovascular_resting_heart_rate_shift')).one()
    excluded = {row['action_code']: row for row in prediction.evidence['excluded_actions']}
    assert excluded['additional_vital_sign_monitoring']['reason'] == 'contraindicated'
    assert prediction.evidence['active_clinical_alerts'][0]['severity'] == 'critical'
    session.refresh(alert)
    assert alert.severity == 'critical' and alert.status == 'open'


def test_mission_and_spacecraft_analysis(client, session, crew):
    for key in ('astronaut', 'second'):
        PredictiveService(session, crew.people['surgeon']).analyze_astronaut(crew.people[key].id, crew.mission.id)
    assert client.post(f'/v1/predictions/missions/{crew.mission.id}/analyze', headers=crew.headers(session, 'astronaut')).status_code == 403
    response = client.post(f'/v1/predictions/missions/{crew.mission.id}/analyze', headers=crew.headers(session, 'admin'))
    assert response.status_code == 200, response.text
    view = response.json()
    found = predictions_of(view)
    assert found['food_expiration']['risk_level'] == 'moderate'
    assert found['medicine_supply_insufficient_data']['prediction_kind'] == 'insufficient_data'
    assert found['food_supply_insufficient_data']['prediction_kind'] == 'insufficient_data'
    assert found['collective_fatigue']['factors'][0] == {'affected_astronauts': 2, 'analyzed_astronauts': 2}
    assert view['context']['astronauts_analyzed'] == 2
    assert 'food_inventory_verification' in {row['action']['code'] for row in view['recommendations']}
    viewer = client.get(f'/v1/predictions/missions/{crew.mission.id}', headers=crew.headers(session, 'astronaut')).json()
    assert viewer['can_analyze'] is False and viewer['latest']['id'] == view['latest']['id']
    assert client.get(f'/v1/predictions/missions/{crew.mission.id}', headers=crew.headers(session, 'outsider')).status_code == 404
    PredictiveService(session, None).analyze_spacecraft(crew.vehicle.id, trigger='scheduled')
    vehicle = client.get(f'/v1/predictions/spacecraft/{crew.vehicle.id}', headers=crew.headers(session, 'admin')).json()
    assert predictions_of(vehicle)['technical_failure_insufficient_data']['prediction_kind'] == 'insufficient_data'
    assert vehicle['context']['usage']['missions'] == 1
    dashboard = client.get('/v1/predictions/dashboard', headers=crew.headers(session, 'surgeon')).json()
    assert dashboard['monitored_missions'] == 1 and dashboard['monitored_astronauts'] == 2
    assert dashboard['pending_recommendations'] > 0


def test_failed_analysis_is_recorded_and_retried(session, crew, monkeypatch):
    service = PredictiveService(session, crew.people['surgeon'])
    original = PredictiveService.store_predictions

    def broken(self, *args, **kwargs):
        raise RuntimeError('synthetic failure')

    monkeypatch.setattr(PredictiveService, 'store_predictions', broken)
    with pytest.raises(HTTPException) as failure:
        service.analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    assert failure.value.status_code == 503
    run = session.exec(select(PredictionRun)).one()
    assert run.status == 'failed' and run.attempts == 1 and 'synthetic failure' in run.error
    monkeypatch.setattr(PredictiveService, 'store_predictions', original)
    retried = service.analyze_astronaut(crew.people['astronaut'].id, crew.mission.id)
    assert retried.id == run.id and retried.status == 'completed' and retried.attempts == 2


def register_model(session, version, result):
    model = PredictionModel(name='astronaut_elevated_fatigue_24h', kind='supervised', subject_type='astronaut', risk_type='elevated_fatigue_24h', version=version,
                            predicted_outcome='elevated_fatigue_24h', horizon_hours=24, status='candidate' if result['passed'] else 'rejected',
                            validation_metrics={key: value for key, value in result.items() if key not in ('artifact', 'artifact_sha256')},
                            artifact=result['artifact'], artifact_sha256=result['artifact_sha256'], model_metadata={'training_source': 'synthetic test data'})
    session.add(model)
    session.commit()
    return model


def test_model_lifecycle_requires_admin_and_supports_rollback(client, session, crew):
    result = train_outcome_model(fatigue_cohort(), rules_config())
    assert result['passed'], result['reasons']
    first = register_model(session, 'v1', result)
    second = register_model(session, 'v2', result)
    rejected = register_model(session, 'v0', {**result, 'passed': False})
    surgeon = crew.headers(session, 'surgeon')
    admin = crew.headers(session, 'global')
    assert client.post(f'/v1/prediction-models/{first.id}/approve', headers=surgeon).status_code == 403
    assert client.post(f'/v1/prediction-models/{rejected.id}/approve', headers=admin).status_code == 409
    assert client.post(f'/v1/prediction-models/{first.id}/activate', headers=admin).status_code == 409
    for model in (first, second):
        assert client.post(f'/v1/prediction-models/{model.id}/approve', headers=admin).json()['status'] == 'approved'
    assert client.post(f'/v1/prediction-models/{first.id}/activate', headers=admin).json()['status'] == 'active'
    sparse = client.post(f'/v1/predictions/astronauts/{crew.people["astronaut"].id}/analyze?mission_id={crew.mission.id}', headers=surgeon).json()
    unavailable = predictions_of(sparse)['elevated_fatigue_24h_insufficient_data']
    assert unavailable['prediction_kind'] == 'insufficient_data' and 'missing' in unavailable['data_quality']['reason']
    now = datetime.now(timezone.utc)
    for days_ago in range(40, 0, -1):
        observation(session, crew.people['astronaut'], crew.people['surgeon'], crew.mission, 'heart_rate', 62 + days_ago % 3, (now - timedelta(days=days_ago)).replace(hour=9), activity='rest')
    session.commit()
    analysis = client.post(f'/v1/predictions/astronauts/{crew.people["astronaut"].id}/analyze?mission_id={crew.mission.id}', headers=surgeon).json()
    ml = [row for row in analysis['latest']['predictions'] if row['prediction_kind'] == 'ml']
    assert len(ml) == 1 and ml[0]['probability_valid'] is True and 0 <= ml[0]['calibrated_probability'] <= 1
    assert analysis['latest']['model_versions']['models'] == ['astronaut_elevated_fatigue_24h:v1']
    assert client.post(f'/v1/prediction-models/{second.id}/activate', headers=admin).json()['status'] == 'active'
    session.expire_all()
    assert session.get(PredictionModel, first.id).status == 'retired'
    assert client.post(f'/v1/prediction-models/{first.id}/activate', headers=admin).json()['status'] == 'active'
    session.expire_all()
    assert session.get(PredictionModel, second.id).status == 'retired'
    metrics = client.get(f'/v1/prediction-models/{first.id}/metrics', headers=surgeon).json()
    assert metrics['validation_metrics']['metrics']['pr_auc'] is not None
    assert all('artifact' not in row for row in client.get('/v1/prediction-models', headers=surgeon).json())
