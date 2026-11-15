from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlmodel import Session

from app.models.mission_risks import MissionOccurrence
from app.models.predictive import PredictionRun
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.services.predictive.data_collection import mission_status_at
from app.services.predictive.mission_risk import MissionRiskPredictionService
from scripts.seed_synthetic_missions import DEFAULT_REFERENCE, schedule
from tests.test_predictive_postgres import predictive_engine


def test_schedule_has_exact_distribution_and_nonoverlapping_reused_spacecraft():
    reference = datetime.fromisoformat(DEFAULT_REFERENCE)
    specs = schedule(reference)
    assert len(specs) == len({row['name'] for row in specs}) == 50
    assert Counter(row['status'] for row in specs) == {'completed': 35, 'in_progress': 10, 'planned': 5}
    assert schedule(reference) == specs
    completed = [row for row in specs if row['status'] == 'completed']
    assert all(row['start'] < row['cutoff'] < row['end'] < reference for row in completed)
    assert all(left['end'] < right['start'] for left, right in zip(completed, completed[1:]))
    assert all(row['start'] < reference < row['end'] for row in specs[35:45])
    assert all(reference < row['start'] for row in specs[45:])
    assert set(row['scenario'] for row in specs[30:]) == set(row['scenario'] for row in specs[:30])


def test_mission_status_uses_only_dates_at_cutoff():
    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc)
    mission = Mission(name='Synthetic', planned_launch_at=cutoff - timedelta(days=4), started_at=cutoff - timedelta(days=3),
                      ended_at=cutoff + timedelta(days=2), status='completed')
    assert mission_status_at(mission, cutoff) == 'in_progress'
    assert mission_status_at(mission, cutoff - timedelta(days=5)) == 'planned'
    assert mission_status_at(mission, cutoff + timedelta(days=3)) == 'completed'


def test_future_runs_events_and_confirmations_do_not_enter_history(predictive_engine):
    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc)
    with Session(predictive_engine) as session:
        user = User(name='Synthetic', email='temporal@example.test', hashed_password='!', is_astronaut=True)
        mission = Mission(name='Synthetic', planned_launch_at=cutoff - timedelta(days=10), started_at=cutoff - timedelta(days=10))
        session.add_all([user, mission])
        session.flush()
        session.add(MissionMember(mission_id=mission.id, user_id=user.id, role='astronaut'))
        for offset in (-1, 1):
            session.add(PredictionRun(subject_type='astronaut', subject_id=user.id, mission_id=mission.id, as_of=cutoff + timedelta(days=offset),
                engine_version='test', model_versions={}, trigger='scheduled', idempotency_key=str(offset), status='completed'))
        for event_offset, confirmation_offset in ((-3, -2), (-2, 1), (1, 2)):
            session.add(MissionOccurrence(mission_id=mission.id, category='spacecraft', phase='in_flight', event_at=cutoff + timedelta(days=event_offset),
                recorded_at=cutoff - timedelta(days=2), confirmed_at=cutoff + timedelta(days=confirmation_offset),
                confirmed_by_user_id=user.id, author_user_id=user.id, severity='warning', source_references=[{'source': 'synthetic:temporal-test'}], description='Synthetic', actions='Review', outcome='Reviewed'))
        session.commit()
        collector = MissionRiskPredictionService(session)
        _, runs = collector.latest_astronaut_runs(mission.id, cutoff)
        assert runs[user.id].as_of < cutoff
        data, _ = collector.collect(mission.id, cutoff)
        assert len(data['occurrences']) == 1
        assert data['occurrences'][0].confirmed_at < cutoff


def test_documents_imported_or_indexed_after_cutoff_are_unavailable(predictive_engine):
    from app.models.knowledge import KnowledgeDocument
    from app.services.mission_rag import MissionRagService
    from tests.test_predictive_postgres import UnavailableRag

    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc)
    with Session(predictive_engine) as session:
        for index, (import_offset, index_offset) in enumerate(((-1, 1), (1, 1))):
            session.add(KnowledgeDocument(title='Synthetic future reference', source_url=f'urn:synthetic:future:{index}', revision='fixture',
                source_origin='SYNTHETIC', is_public=True, indexing_status='completed', imported_at=cutoff + timedelta(days=import_offset),
                indexed_at=cutoff + timedelta(days=index_offset)))
        session.commit()
        assert MissionRagService(session, UnavailableRag()).search('sleep', as_of=cutoff) == []


def test_future_receipts_and_consumption_do_not_change_expiration_balance(predictive_engine):
    from app.models.nutrition import FoodProduct, FoodStockMovement, MissionFoodLot

    cutoff = datetime(2026, 1, 10, tzinfo=timezone.utc)
    with Session(predictive_engine) as session:
        user = User(name='Synthetic', email='stock@example.test', hashed_password='!')
        mission = Mission(name='Synthetic stock', planned_launch_at=cutoff - timedelta(days=10))
        product = FoodProduct(name='Synthetic food', category='food', preservation_method='thermostabilized', physical_form='solid',
                              reference_quantity=100, reference_unit='g', reference_basis='stored', preparation_method='ready_to_consume')
        session.add_all([user, mission, product])
        session.flush()
        lot = MissionFoodLot(mission_id=mission.id, food_product_id=product.id, lot_code='A', initial_quantity=1000,
                             remaining_quantity=100, stock_unit='g', expiration_date=(cutoff + timedelta(days=2)).date())
        future_lot = MissionFoodLot(mission_id=mission.id, food_product_id=product.id, lot_code='B', initial_quantity=1000,
                             remaining_quantity=1000, stock_unit='g', expiration_date=(cutoff + timedelta(days=2)).date())
        session.add_all([lot, future_lot])
        session.flush()
        for target, quantity, offset in ((lot, 1000, -1), (lot, -900, 1), (future_lot, 1000, 1)):
            at = cutoff + timedelta(days=offset)
            session.add(FoodStockMovement(lot_id=target.id, quantity=quantity, stock_unit='g', movement_type='initial' if quantity > 0 else 'consumption',
                purpose='fixture', recorded_by_user_id=user.id, recorded_at=at,
                risk_snapshot={'reference_delta': str(quantity / 100), 'event_at': at.isoformat(), 'food_name': product.name,
                               'expiration_date': target.expiration_date.isoformat(), 'unit': 'g', 'quantity_per_reference': '100'}))
        session.commit()
        data, _ = MissionRiskPredictionService(session).collect(mission.id, cutoff)
        assert len(data['lots']) == 1
        assert data['lots'][0].remaining_quantity == 1000


def test_verification_scopes_synthetic_missions_without_counting_existing_records(predictive_engine):
    from scripts.seed_synthetic_missions import verify

    reference = datetime.fromisoformat(DEFAULT_REFERENCE)
    with Session(predictive_engine) as session:
        existing = Mission(name='Preexisting mission', planned_launch_at=reference, status='planned')
        session.add(existing)
        session.flush()
        missions = [Mission(name=row['name'], planned_launch_at=row['start'], status=row['status'],
                            started_at=row['start'] if row['status'] != 'planned' else None,
                            ended_at=row['end'] if row['status'] == 'completed' else None) for row in schedule(reference)]
        session.add_all(missions)
        session.flush()
        result = verify(session, [mission.id for mission in missions])
        assert result['missions'] == {'completed': 35, 'in_progress': 10, 'planned': 5}
        assert session.get(Mission, existing.id).name == 'Preexisting mission'
