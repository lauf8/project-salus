from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
import os
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx
from pypdf import PdfWriter
import pytest
from sqlalchemy import func, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import engine, get_session
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.knowledge import KnowledgeDocument, KnowledgePassage
from app.models.mission_risks import MissionOccurrence, MissionRiskAction, MissionRiskAlert, MissionRiskEvaluation, MissionRiskPlan
from app.models.notifications import HealthNotification
from app.models.nutrition import FoodProduct, FoodStockMovement, MissionFoodLot
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.mission_risks import OccurrenceInput, RiskActionInput, RiskPlanInput
from app.schemas.nutrition import FoodLotCreate
from app.services.food_risk_rule import project_food
from app.services.mission_rag import MissionRagService, OllamaRag, RagSettings, split_pages, validate_guidance
from app.services.mission_risk_service import MissionRiskService
from app.services.nutrition_service import NutritionService
from scripts.create_risk_demo_pdf import synthetic_pdf


class FakeRag:
    settings = RagSettings(minimum_similarity=0.1)

    def embed(self, texts):
        return [[1.0, 0.0, 0.0] for _ in texts]

    def generate(self, context, sources):
        return validate_guidance({'action': 'Verify lot counts and replenish with mission control.', 'responsible_role': 'nutritionist', 'citation_ids': [sources[0]['id']]}, sources)


@pytest.fixture
def risk_engine():
    if os.getenv('MISSION_RISKS_POSTGRES_TESTS') != '1':
        pytest.skip('Requires isolated PostgreSQL schemas')
    schema = 'risk_test_' + uuid4().hex
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


@pytest.fixture
def risk_session(risk_engine):
    with Session(risk_engine) as session:
        yield session


def setup_food(session):
    now = datetime.now(timezone.utc)
    admin = User(name='Synthetic mission administrator', email='risk-admin@example.test', hashed_password='!', is_global_admin=True, is_mission_admin=True)
    mission = Mission(name='Synthetic food mission', planned_launch_at=now - timedelta(days=2), started_at=now - timedelta(days=2), crew_size=2)
    food = FoodProduct(name='Synthetic rice', category='food', preservation_method='thermostabilized', physical_form='solid', reference_quantity=100, reference_unit='g', reference_basis='stored', preparation_method='ready_to_consume')
    session.add_all([admin, mission, food])
    session.flush()
    session.add(MissionMember(mission_id=mission.id, user_id=admin.id, role='mission_admin'))
    session.commit()
    return admin, mission, food


def planning(mission, food, **changes):
    now = datetime.now(timezone.utc)
    values = {'planned_end_at': now + timedelta(days=8), 'exposure_start_at': mission.started_at or mission.planned_launch_at, 'crew_size': 2, 'inventory_complete': True,
              'daily_rates': [{'food_product_id': food.id, 'quantity': '100', 'unit': 'g', 'basis': 'stored', 'per_person': True}]}
    return RiskPlanInput(**{**values, **changes})


def test_fefo_and_expiration_exclusion():
    start = datetime(2026, 1, 1).date()
    result = project_food([{'id': 2, 'quantity': '10', 'expiration_date': '2026-01-01'}, {'id': 1, 'quantity': '2', 'expiration_date': '2026-01-08'}], '3', start, start + timedelta(days=2))
    assert result['daily_projection'][0]['allocations'][0]['lot_id'] == 2
    assert result['daily_projection'][1]['expired'] == '7'
    assert result['first_shortage_date'] == '2026-01-02'
    assert result['severity'] == 'critical'


def test_chunk_pages_and_citation_allowlist():
    chunks = split_pages([(1, 'Inventory\n' + 'a' * 450), (2, 'Expiry\n' + 'b' * 450)], 200, 30)
    assert {chunk['page_number'] for chunk in chunks} == {1, 2}
    assert chunks[1]['passage_order'] == 1
    with pytest.raises(ValueError):
        validate_guidance({'action': 'Check stock', 'responsible_role': 'nutritionist', 'citation_ids': [999]}, [{'id': 1}])
    with pytest.raises(ValueError):
        split_pages([(1, 'text')], 200, 200)


def test_pdf_import_dedup_failure_retry_and_page_retrieval(risk_session):
    service = MissionRagService(risk_session, FakeRag())
    imported = service.import_pdf(synthetic_pdf(), 'Synthetic NASA reference fixture', 'https://www.nasa.gov/synthetic-fixture', '1')
    duplicate = service.import_pdf(synthetic_pdf(), 'Duplicate', '', '1')
    assert duplicate['id'] == imported['id']
    class OfflineRag(FakeRag):
        def embed(self, texts):
            raise httpx.ConnectError('Ollama offline')
    failed = MissionRagService(risk_session, OfflineRag()).process(imported['id'])
    assert failed['indexing_status'] == 'failed'
    assert 'Ollama' in failed['indexing_error']
    indexed = service.process(imported['id'])
    assert indexed['indexing_status'] == 'completed'
    assert indexed['embedding_dimension'] == 3
    result = service.search('food inventory')
    assert result[0]['page'] == 1
    assert result[0]['document_id'] == imported['id']
    assert result[0]['origin'] == 'NASA'
    service.rag.settings = RagSettings(embedding_model='different-model')
    assert service.documents()[0]['reindex_required']
    assert service.search('food inventory') == []


def test_pdf_without_text_fails_clearly(risk_session):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buffer = BytesIO()
    writer.write(buffer)
    service = MissionRagService(risk_session, FakeRag())
    document = service.import_pdf(buffer.getvalue(), 'Image-only fixture', '', '1')
    response = service.process(document['id'])
    assert response['indexing_status'] == 'failed'
    assert 'OCR' in response['indexing_error']
    assert service.process(document['id'])['indexing_status'] == 'failed'


def test_missing_data_and_normalized_demand(risk_session):
    admin, mission, food = setup_food(risk_session)
    service = MissionRiskService(risk_session, admin)
    assert service.calculate(mission.id)['state'] == 'inconclusive'
    plan = service.save_plan(mission.id, planning(mission, food, inventory_complete=False))
    assert service.calculate(mission.id)['state'] == 'inconclusive'
    assert not risk_session.exec(select(MissionRiskAlert)).all()
    plan = service.save_plan(mission.id, planning(mission, food, daily_rates=[{'food_product_id': food.id, 'quantity': '0.1', 'unit': 'kg', 'per_person': True}]))
    assert Decimal(plan.daily_rates[0]['daily_references']) == 2
    result = service.calculate(mission.id)
    assert result['items'][0]['state'] == 'risk'
    assert result['items'][0]['history']['sufficient_coverage_missions'] == 0


def test_concurrent_evaluations_deduplicate_alert_and_notifications(risk_session, risk_engine):
    admin, mission, food = setup_food(risk_session)
    service = MissionRiskService(risk_session, admin)
    service.save_plan(mission.id, planning(mission, food))
    ids = admin.id, mission.id
    risk_session.commit()
    def evaluate(_):
        with Session(risk_engine) as session:
            return MissionRiskService(session, session.get(User, ids[0])).evaluate(ids[1]).id
    with ThreadPoolExecutor(max_workers=2) as executor:
        evaluations = list(executor.map(evaluate, range(2)))
    assert len(set(evaluations)) == 2
    assert risk_session.exec(select(func.count()).select_from(MissionRiskAlert).where(MissionRiskAlert.status != 'resolved')).one() == 1
    assert risk_session.exec(select(func.count()).select_from(HealthNotification)).one() == 1


def test_guidance_failure_preserves_stock_and_alert(risk_session, monkeypatch):
    admin, mission, food = setup_food(risk_session)
    stock = NutritionService(risk_session, admin)
    lot = stock.create_lot(mission.id, FoodLotCreate(food_product_id=food.id, lot_code='TEST-1', expiration_date=datetime.now(timezone.utc).date() + timedelta(days=10), initial_quantity='100', stock_unit='g', stock_basis='stored'))
    service = MissionRiskService(risk_session, admin)
    service.save_plan(mission.id, planning(mission, food))
    alert = risk_session.exec(select(MissionRiskAlert)).one()
    def offline(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(MissionRagService, 'search', offline)
    updated = service.guidance(mission.id, alert.id)
    assert updated.guidance['state'] == 'rag_unavailable'
    assert updated.status == 'open'
    assert risk_session.get(MissionFoodLot, lot.id).remaining_quantity == 100
    assert risk_session.exec(select(FoodStockMovement)).one().risk_snapshot['reference_delta'] == '1'


def test_permissions_assignment_read_execution_and_confirmation(risk_session):
    admin, mission, food = setup_food(risk_session)
    observer = User(name='Observer', email='observer@risk.test', hashed_password='!', is_observer=True)
    astronaut = User(name='Crew', email='crew@risk.test', hashed_password='!', is_astronaut=True)
    risk_session.add_all([observer, astronaut]);risk_session.flush()
    risk_session.add_all([MissionMember(mission_id=mission.id, user_id=observer.id, role='observer'), MissionMember(mission_id=mission.id, user_id=astronaut.id, role='astronaut')]);risk_session.commit()
    manager = MissionRiskService(risk_session, admin)
    manager.save_plan(mission.id, planning(mission, food))
    alert = risk_session.exec(select(MissionRiskAlert)).one()
    with pytest.raises(HTTPException) as denied:
        MissionRiskService(risk_session, observer).evaluate(mission.id)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException):
        MissionRiskService(risk_session, astronaut).action(mission.id, alert.id, RiskActionInput(action='execute', details='Unassigned'))
    manager.action(mission.id, alert.id, RiskActionInput(action='assign', details='Verify counts', responsible_user_id=astronaut.id))
    crew = MissionRiskService(risk_session, astronaut)
    assert len(crew.assigned()) == 1
    crew.action(mission.id, alert.id, RiskActionInput(action='read', details='Read procedure'))
    crew.action(mission.id, alert.id, RiskActionInput(action='execute', details='Checked all usable lots'))
    with pytest.raises(HTTPException):
        crew.action(mission.id, alert.id, RiskActionInput(action='resolve', details='Not authorized'))
    assert risk_session.exec(select(func.count()).select_from(MissionOccurrence)).one() == 0
    event = manager.record_occurrence(mission.id, OccurrenceInput(food_product_id=food.id, phase='in_flight', event_at=datetime.now(timezone.utc) - timedelta(hours=1), severity='warning', source_references=[{'record_id': 'synthetic-log-1'}], description='Observed supply interruption', actions='Counted lots', outcome='Resupply requested'))
    assert event.confirmed_at is None
    manager.confirm_occurrence(mission.id, event.id)
    assert event.confirmed_at is not None


def test_replay_excludes_future_records_and_mutable_product_values(risk_session):
    admin, mission, food = setup_food(risk_session)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=1)
    service = MissionRiskService(risk_session, admin)
    plan = service.save_plan(mission.id, planning(mission, food, planned_end_at=now))
    assert service.calculate(mission.id, cutoff, replay=True)['items'] == []
    plan.recorded_at = cutoff - timedelta(days=1)
    risk_session.add(plan)
    lot = MissionFoodLot(mission_id=mission.id, food_product_id=food.id, lot_code='Historical', expiration_date=now.date() + timedelta(days=1), initial_quantity=100, remaining_quantity=100, stock_unit='g')
    risk_session.add(lot);risk_session.flush()
    snapshot = {'reference_delta': '1', 'event_at': (cutoff - timedelta(days=1)).isoformat(), 'food_name': 'Original rice', 'expiration_date': lot.expiration_date.isoformat(), 'unit': 'g', 'quantity_per_reference': '100'}
    old = FoodStockMovement(lot_id=lot.id, quantity=100, stock_unit='g', movement_type='initial', purpose='receipt', recorded_by_user_id=admin.id, recorded_at=cutoff - timedelta(days=1), risk_snapshot=snapshot)
    late = FoodStockMovement(lot_id=lot.id, quantity=100, stock_unit='g', movement_type='initial', purpose='receipt', recorded_by_user_id=admin.id, recorded_at=now, risk_snapshot=snapshot)
    risk_session.add_all([old, late]);risk_session.commit()
    result = service.calculate(mission.id, cutoff, replay=True)
    assert result['input_references']['movement_ids'] == [old.id]
    assert result['items'][0]['current_balance'] == '1'
    food.reference_quantity = 9999;food.name = 'Future rename';risk_session.add(food);risk_session.commit()
    assert service.calculate(mission.id, cutoff, replay=True) == result
    mission.ended_at = now;mission.status = 'completed';risk_session.add(mission);risk_session.commit()
    notifications = risk_session.exec(select(func.count()).select_from(HealthNotification)).one()
    replay = service.replay(mission.id, cutoff, now)
    assert replay['notifications_sent'] == 0
    assert risk_session.exec(select(func.count()).select_from(HealthNotification)).one() == notifications
    assert late.id not in replay['chronology'][0]['input_references']['movement_ids']


def test_historical_frequency_counts_only_covered_confirmed_missions(risk_session):
    admin, mission, food = setup_food(risk_session)
    service = MissionRiskService(risk_session, admin)
    now = datetime.now(timezone.utc)
    current = service.save_plan(mission.id, planning(mission, food))
    for index in range(3):
        start = now - timedelta(days=50 + index * 20)
        old_mission = Mission(name=f'Previous {index}', planned_launch_at=start, started_at=start, ended_at=start + timedelta(days=11), status='completed')
        risk_session.add(old_mission);risk_session.flush()
        previous = MissionRiskPlan(mission_id=old_mission.id, exposure_start_at=start, planned_end_at=start + timedelta(days=11), crew_size=2, consumption_window_days=7, inventory_complete=True, consumption_complete=index != 2, coverage_start=start, coverage_end=start + timedelta(days=11), daily_rates=current.daily_rates, recorded_at=start, author_user_id=admin.id)
        risk_session.add(previous)
        risk_session.add(MissionRiskEvaluation(mission_id=old_mission.id, rule_version='food-fefo-v1', evaluated_at=start + timedelta(days=11), recorded_at=start + timedelta(days=11), state='evaluated', results={'mission_snapshot': {'status': 'completed', 'ended_at': (start + timedelta(days=11)).isoformat()}}))
        event = MissionOccurrence(mission_id=old_mission.id, category='food_shortage', food_product_id=food.id, phase='in_flight', event_at=start + timedelta(days=5), recorded_at=start + timedelta(days=6), confirmed_at=start + timedelta(days=6) if index == 0 else None, confirmed_by_user_id=admin.id if index == 0 else None, author_user_id=admin.id, severity='warning', source_references=[{'record_id': f'historical-{index}'}], description='Synthetic event', actions='Checked counts', outcome='Resupplied')
        risk_session.add(event)
    risk_session.commit()
    history = service.comparable_history(mission.id, current, food.id, Decimal(2), now)
    assert history['eligible_missions'] == 3
    assert history['sufficient_coverage_missions'] == 2
    assert history['confirmed_occurrence_missions'] == 1


def test_upload_route_and_observer_permissions(risk_session):
    admin, mission, food = setup_food(risk_session)
    def override_session():
        yield risk_session
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        client = TestClient(app)
        response = client.post('/v1/risk-documents', data={'title': 'Synthetic PDF', 'revision': '1'}, files={'file': ('fixture.pdf', synthetic_pdf(), 'application/pdf')})
        assert response.status_code == 201, response.text
        assert 'pdf_data' not in response.json()
        admin.is_global_admin = False;admin.is_mission_admin = False;admin.is_observer = True
        risk_session.add(admin);risk_session.commit()
        denied = client.post('/v1/risk-documents', data={'title': 'Denied', 'revision': '1'}, files={'file': ('fixture.pdf', synthetic_pdf(), 'application/pdf')})
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(os.getenv('MISSION_RISKS_REAL_OLLAMA') != '1', reason='Requires real Ollama embedding and generation models')
def test_real_ollama_pdf_index_search_and_generation(risk_session):
    rag = OllamaRag()
    capabilities = rag.capabilities()
    assert rag.settings.embedding_model in capabilities['capabilities']
    service = MissionRagService(risk_session, rag)
    imported = service.import_pdf(synthetic_pdf(), 'Synthetic food inventory verification fixture', '', '1')
    indexed = service.process(imported['id'])
    assert indexed['indexing_status'] == 'completed', indexed
    sources = service.search('Verify food inventory daily and consume lots with earliest expiration first')
    assert sources and sources[0]['page'] == 1
    result = rag.generate({'risk_type': 'food_shortage', 'food_name': 'Synthetic rice', 'shortage_date': '2026-12-01'}, sources)
    assert set(result['citation_ids']).issubset({source['id'] for source in sources})
    print(f"Real Ollama: model={indexed['embedding_model']} dimensions={indexed['embedding_dimension']} generation={rag.settings.generation_model} page={sources[0]['page']}")


def test_complete_food_risk_http_flow(risk_session, monkeypatch):
    import app.services.mission_rag as rag_module
    monkeypatch.setattr(rag_module, 'OllamaRag', FakeRag)
    admin, mission, food = setup_food(risk_session)
    astronaut = User(name='Synthetic astronaut', email='flow-crew@risk.test', hashed_password='!', is_astronaut=True)
    risk_session.add(astronaut);risk_session.flush()
    member = MissionMember(mission_id=mission.id, user_id=astronaut.id, role='astronaut')
    risk_session.add(member);risk_session.commit()
    def override_session():
        yield risk_session
    app.dependency_overrides[get_session] = override_session
    try:
        client = TestClient(app)
        admin_headers = {'X-Public-User': str(admin.id), 'X-Public-Profile': 'is_global_admin'}
        crew_headers = {'X-Public-User': str(astronaut.id), 'X-Public-Profile': 'is_astronaut'}
        base = f'/v1/missions/{mission.id}'
        response = client.post(base + '/food-lots', headers=admin_headers, json={'food_product_id': food.id, 'lot_code': 'FLOW-1', 'expiration_date': (datetime.now(timezone.utc).date() + timedelta(days=20)).isoformat(), 'initial_quantity': '600', 'stock_unit': 'g', 'stock_basis': 'stored'})
        assert response.status_code == 201, response.text
        lot_id = response.json()['id']
        response = client.post(base + '/risks/plans', headers=admin_headers, json=planning(mission, food).model_dump(mode='json'))
        assert response.status_code == 201, response.text
        response = client.post(base + '/meal-logs', headers=crew_headers, json={'mission_member_id': member.id, 'consumed_at': datetime.now(timezone.utc).isoformat(), 'meal_type': 'lunch', 'items': [{'food_product_id': food.id, 'lot_id': lot_id, 'consumed_quantity': '100', 'consumed_unit': 'g', 'consumed_basis': 'stored'}]})
        assert response.status_code == 201, response.text
        state = client.get(base + '/risks', headers=admin_headers).json()
        assert len(state['alerts']) == 1
        alert = state['alerts'][0]
        assert alert['assessment']['current_balance'] == '5'
        assert alert['assessment']['first_shortage_date']
        imported = client.post('/v1/risk-documents', headers=admin_headers, data={'title': 'Synthetic food procedure', 'revision': '1'}, files={'file': ('test.pdf', synthetic_pdf(), 'application/pdf')})
        assert imported.status_code == 201
        indexed = client.post(f"/v1/risk-documents/{imported.json()['id']}/process", headers=admin_headers)
        assert indexed.json()['indexing_status'] == 'completed'
        guided = client.post(base + f"/risks/{alert['id']}/guidance", headers=admin_headers)
        assert guided.status_code == 200, guided.text
        assert guided.json()['guidance']['sources'][0]['page'] == 1
        assert guided.json()['guidance']['documentary_evidence']
        assigned = client.post(base + f"/risks/{alert['id']}/actions", headers=admin_headers, json={'action': 'assign', 'details': 'Assign operational verification', 'responsible_user_id': astronaut.id})
        assert assigned.status_code == 200
        pending = client.get(base + '/risks', headers=crew_headers).json()['alerts'][0]['guidance']
        assert pending['state'] == 'awaiting_team_review'
        assert pending['sources'] == []
        rejected = client.post(base + f"/risks/{alert['id']}/actions", headers=admin_headers, json={'action': 'approve_guidance', 'details': 'Clinical review denied for non-physician', 'guidance_kind': 'clinical'})
        assert rejected.status_code == 403
        approved = client.post(base + f"/risks/{alert['id']}/actions", headers=admin_headers, json={'action': 'approve_guidance', 'details': 'Approved operational stock procedure', 'guidance_kind': 'operational'})
        assert approved.status_code == 200
        for action, actor in [('read', crew_headers), ('execute', crew_headers), ('resolve', admin_headers)]:
            response = client.post(base + f"/risks/{alert['id']}/actions", headers=actor, json={'action': action, 'details': f'Synthetic {action} trace', 'responsible_user_id': astronaut.id if action == 'assign' else None})
            assert response.status_code == 200, response.text
        assert response.json()['status'] == 'resolved'
        assert risk_session.exec(select(func.count()).select_from(MissionOccurrence)).one() == 0
        assert len(client.get(base + f"/risks/{alert['id']}/actions", headers=admin_headers).json()) == 5
        assert client.get('/v1/mission-risks/assigned', headers=crew_headers).json() == []
    finally:
        app.dependency_overrides.clear()


def test_legacy_document_enrichment_preserves_passages(risk_session):
    legacy = KnowledgeDocument(title='Legacy reference', source_url='https://www.nasa.gov/legacy-fixture', revision='1', is_public=True)
    risk_session.add(legacy);risk_session.flush()
    passage = KnowledgePassage(document_id=legacy.id, section='Original inventory section', content='Existing food inventory guidance.', topic_codes=['food_shortage'], page_number=1)
    risk_session.add(passage);risk_session.commit()
    passage_id = passage.id
    service = MissionRagService(risk_session, FakeRag())
    imported = service.import_pdf(synthetic_pdf(), 'Existing reference PDF', legacy.source_url, '1')
    assert imported['id'] == legacy.id
    assert service.process(legacy.id)['indexing_status'] == 'completed'
    assert risk_session.get(KnowledgePassage, passage_id).content == 'Existing food inventory guidance.'


def test_replay_persists_lead_time_and_intervention_without_notifications(risk_session):
    admin, mission, food = setup_food(risk_session)
    service = MissionRiskService(risk_session, admin)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=1)
    plan = service.save_plan(mission.id, planning(mission, food, planned_end_at=now))
    plan.recorded_at = start - timedelta(days=1)
    risk_session.add(plan)
    mission.ended_at = now;mission.status = 'completed';risk_session.add(mission)
    event = MissionOccurrence(mission_id=mission.id, category='food_shortage', food_product_id=food.id, phase='in_flight', event_at=start + timedelta(hours=12), recorded_at=now, confirmed_at=now, confirmed_by_user_id=admin.id, author_user_id=admin.id, severity='critical', source_references=[{'record_id': 'synthetic-outcome'}], description='Synthetic final outcome', actions='Resupply', outcome='Intervened', intervention=True)
    risk_session.add(event);risk_session.commit()
    before = risk_session.exec(select(func.count()).select_from(HealthNotification)).one()
    report = service.replay(mission.id, start, now)
    assert report['detected_occurrences'] == [event.id]
    assert report['lead_times'][0]['lead_days'] == 0.5
    assert report['interventions'][0]['occurrence_id'] == event.id
    assert risk_session.get(MissionRiskEvaluation, report['report_id']).state == 'replay'
    assert risk_session.exec(select(func.count()).select_from(HealthNotification)).one() == before


def test_observed_demand_uses_complete_utc_days_without_future_coverage(risk_session):
    admin, mission, food = setup_food(risk_session)
    now = datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=2)
    lot = MissionFoodLot(mission_id=mission.id, food_product_id=food.id, lot_code='OBSERVED', expiration_date=now.date() + timedelta(days=20), initial_quantity=1000, remaining_quantity=600, stock_unit='g')
    risk_session.add(lot);risk_session.flush()
    def snapshot(quantity, at):
        return {'reference_delta': quantity, 'event_at': at.isoformat(), 'food_name': food.name, 'expiration_date': lot.expiration_date.isoformat(), 'unit': 'g', 'quantity_per_reference': '100'}
    risk_session.add(FoodStockMovement(lot_id=lot.id, quantity=1000, stock_unit='g', movement_type='initial', purpose='receipt', recorded_by_user_id=admin.id, recorded_at=start - timedelta(days=1), risk_snapshot=snapshot('10', start - timedelta(days=1))))
    risk_session.add(FoodStockMovement(lot_id=lot.id, quantity=-400, stock_unit='g', movement_type='consumption', purpose='meal', recorded_by_user_id=admin.id, recorded_at=start + timedelta(hours=12), risk_snapshot=snapshot('-4', start + timedelta(hours=12))))
    risk_session.commit()
    service = MissionRiskService(risk_session, admin)
    service.save_plan(mission.id, planning(mission, food, consumption_window_days=2, daily_rates=[], consumption_complete=True, coverage_start=start, coverage_end=end))
    item = service.calculate(mission.id)['items'][0]
    assert item['observed_daily_rate'] == '2'
    assert item['planned_daily_rate'] is None
    assert item['state'] == 'risk'
    assert item['consumption_window']['coverage_confirmed'] is True
    assert item['consumption_window']['end'] == end.isoformat()


def test_synthetic_alert_mission_is_idempotent_and_clinical_access_stays_scoped(risk_session):
    from scripts.seed_risk_alert_mission import PEOPLE, seed_alert_mission
    from app.models.health import HealthObservation
    untouched_admin, untouched_mission, untouched_food = setup_food(risk_session)
    original_name = untouched_mission.name
    first = seed_alert_mission(risk_session)
    second = seed_alert_mission(risk_session)
    assert first['mission_id'] == second['mission_id']
    assert first['synthetic_data'] is True
    assert len(first['clinical_alerts']) == 4
    assert len(first['food_alerts']) == 1
    assert risk_session.exec(select(func.count()).select_from(HealthObservation).where(HealthObservation.mission_id == first['mission_id'])).one() == 4
    risk_session.refresh(untouched_mission)
    assert untouched_mission.name == original_name
    doctor = risk_session.get(User, first['physician']['id'])
    doctor_view = MissionRiskService(risk_session, doctor).health_risks(first['mission_id'])
    assert doctor_view['state'] == 'available'
    assert len(doctor_view['alerts']) == 4
    conditions = {alert['context']['condition'] for alert in doctor_view['alerts']}
    assert {'hypoglycemia_signal', 'respiratory_signal', 'fever_signal'}.issubset(conditions)
    assert all(alert['context']['disease_probability'] is None and not alert['context']['diagnosis_confirmed'] for alert in doctor_view['alerts'])
    astronaut_id = first['astronauts'][0]['id']
    astronaut = risk_session.get(User, astronaut_id)
    own_view = MissionRiskService(risk_session, astronaut).health_risks(first['mission_id'])
    assert len(own_view['alerts']) == 2
    assert all(alert['astronaut_id'] == astronaut_id for alert in own_view['alerts'])
    admin = risk_session.exec(select(User).where(User.email == PEOPLE['admin'][1])).one()
    restricted = MissionRiskService(risk_session, admin).health_risks(first['mission_id'])
    assert restricted['state'] == 'restricted'
    assert restricted['alerts'] == []
