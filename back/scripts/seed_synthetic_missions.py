import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import random
import re
from unittest.mock import patch

from sqlalchemy import func, text, update
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import engine
from app.models import access, care, clinical_records, health_alerts, knowledge, medicines, mental_health, mission_risks, notifications, nutrition, predictive, preflight, revoked_token, space_weather, spacecraft
from app.models.health import HealthObservation
from app.models.user import User
from app.schemas.health import UNITS
from app.schemas.nutrition import FoodProductResponse
from app.services.mission_risk_service import MissionRiskService
from app.services.predictive.data_collection import AstronautDataCollector
from app.services.predictive_service import PredictiveService
from app.services.predictive.knowledge import PredictiveKnowledgeService

DEFAULT_REFERENCE = '2026-11-15T12:00:00+00:00'
VERSION = 'salus-synthetic-50-v1'
SCENARIOS = ('stable', 'isolated', 'progressive', 'sleep_fatigue', 'mental_follow_up', 'body_composition', 'food_supply', 'technical_incident', 'irregular', 'paired_outcomes')


def add(session, model_type, **values):
    row = model_type(**values)
    session.add(row)
    session.flush()
    return row


def schedule(reference):
    rows = []
    cursor = reference - timedelta(days=3200)
    for index in range(50):
        duration = (7, 21, 45, 90, 180)[index % 5]
        status = 'completed' if index < 35 else 'in_progress' if index < 45 else 'planned'
        if status == 'completed':
            start = cursor
            cursor += timedelta(days=duration + 7)
        elif status == 'in_progress':
            start = reference - timedelta(days=14 + (index % 5) * 10)
            duration = max(duration, (reference - start).days + 14)
        else:
            start = reference + timedelta(days=14 + (index - 45) * 30)
        end = start + timedelta(days=duration)
        cutoff = end - timedelta(days=2) if status == 'completed' else reference
        rows.append(dict(index=index, name=f'Salus Synthetic {index + 1:03d}', status=status, start=start, end=end,
                         cutoff=cutoff, crew_size=2 + index % 3, scenario=SCENARIOS[index % 10]))
    return rows


def configuration(seed, reference):
    return {'version': VERSION, 'seed': seed, 'reference': reference.isoformat()}


def observation(session, mission, user, doctor, at, indicator, value, reference=False, delay=20):
    values = {'value': value}
    if indicator == 'blood_pressure':
        values = {'systolic': value[0], 'diastolic': value[1]}
    elif indicator in ('attention', 'consciousness'):
        values = {'category': value}
    session.add(HealthObservation(astronaut_id=user.id, mission_id=mission.id, recorded_by_user_id=doctor.id,
                                 indicator=indicator, collected_at=at, recorded_at=at + timedelta(minutes=delay),
                                 source='self_report' if indicator in ('fatigue', 'mood', 'sleep_quality', 'sleep_duration', 'attention') else 'manual_measurement',
                                 activity='rest', signal_quality='good', symptoms_status='absent',
                                 is_preflight_reference=reference, unit=UNITS.get(indicator), **values))


def movement(session, lot, product, doctor, at, quantity, item=None):
    session.add(nutrition.FoodStockMovement(lot_id=lot.id, meal_log_item_id=item.id if item else None,
        quantity=quantity, stock_unit='g', movement_type='initial' if quantity > 0 else 'consumption',
        purpose='receipt' if quantity > 0 else 'meal', recorded_by_user_id=doctor.id, recorded_at=at,
        risk_snapshot={'reference_delta': str(Decimal(quantity) / Decimal(100)), 'event_at': at.isoformat(),
                       'food_name': product.name, 'expiration_date': lot.expiration_date.isoformat(),
                       'unit': 'g', 'quantity_per_reference': '100'}))


def create_dataset(session, seed, reference):
    rng = random.Random(seed)
    config = configuration(seed, reference)
    doctor = add(session, User, name='Equipe Sintética Médica', email='salus50-doctor@example.test', hashed_password='!', is_physician=True)
    staff = {'flight_surgeon': doctor}
    for role, flag in (('mission_admin', 'is_mission_admin'), ('psychologist', 'is_psychologist'), ('nutritionist', 'is_nutritionist'), ('nurse', 'is_nurse'), ('observer', 'is_observer')):
        staff[role] = add(session, User, name=f'Equipe Sintética {role}', email=f'salus50-{role}@example.test', hashed_password='!', **{flag: True})
    ships = []
    for index in range(16):
        ship = add(session, spacecraft.Spacecraft, name=f'Salus Synthetic Vessel {index + 1:02d}', maximum_crew_capacity=4,
                   model=f'Simulator {index % 3 + 1}', manufacturer='Salus Synthetic', manufactured_year=max(1, reference.year - 16 + index % 5),
                   status='in_use' if 1 <= index <= 10 else 'available')
        ships.append(ship)
        for module_index in range(1 + index % 3):
            add(session, spacecraft.SpacecraftModule, spacecraft_id=ship.id, code=f'M{module_index + 1}', name=f'Módulo Sintético {module_index + 1}',
                is_pressurized=True, is_habitable=True, pressurized_volume_m3=30 + module_index * 10,
                technical_specifications={'dataset': config} if index == 0 and module_index == 0 else {})
    product = add(session, nutrition.FoodProduct, name='Refeição composta sintética', category='food', preservation_method='thermostabilized',
                  physical_form='solid', reference_quantity=100, reference_unit='g', reference_basis='stored', preparation_method='ready_to_consume',
                  energy_kcal=200, protein_g=10, carbohydrate_g=25, fat_g=6, fiber_g=3, sodium_mg=180)
    ingredient = add(session, medicines.ActiveIngredient, name='Ingrediente sintético A')
    medicine = add(session, medicines.Medicine, name='Medicamento sintético A', main_indications='Simulação de registro')
    session.add(medicines.MedicineActiveIngredient(medicine_id=medicine.id, active_ingredient_id=ingredient.id))
    exam_type = add(session, preflight.ExamType, code='salus50_screening', name='Avaliação pré-voo sintética')
    for spec in schedule(reference):
        index, start, end, cutoff = (spec[key] for key in ('index', 'start', 'end', 'cutoff'))
        mission = add(session, preflight.Mission, name=spec['name'], crew_size=spec['crew_size'], status=spec['status'],
                      spacecraft_id=None if index % 7 == 0 else ships[0 if index < 35 else index - 34].id,
                      planned_launch_at=start, started_at=None if spec['status'] == 'planned' else start,
                      ended_at=end if spec['status'] == 'completed' else None)
        for role, user in staff.items():
            add(session, preflight.MissionMember, mission_id=mission.id, user_id=user.id, role=role)
        requirement = add(session, preflight.MissionExamRequirement, mission_id=mission.id, exam_type_id=exam_type.id, due_days_before_launch=3)
        last = end - timedelta(days=1) if spec['status'] == 'completed' else reference - timedelta(hours=1)
        days = max(0, (last - start).days + 1) if spec['status'] != 'planned' else 0
        total_consumed = days * spec['crew_size'] * 1200
        reserve = 2 * spec['crew_size'] * 1200 if spec['scenario'] == 'food_supply' else (max(14, (end - last).days + 4)) * spec['crew_size'] * 1200
        total = total_consumed + reserve
        lot = add(session, nutrition.MissionFoodLot, mission_id=mission.id, food_product_id=product.id, lot_code=f'S50-{index + 1:03d}',
                  expiration_date=(cutoff + timedelta(days=3) if spec['scenario'] == 'food_supply' else end + timedelta(days=120)).date(),
                  initial_quantity=total, remaining_quantity=total, stock_unit='g', stock_basis='stored')
        receipt_at = min(start - timedelta(days=10), reference - timedelta(days=1))
        movement(session, lot, product, doctor, receipt_at, total)
        add(session, mission_risks.MissionRiskPlan, mission_id=mission.id, planned_end_at=end, exposure_start_at=start, crew_size=spec['crew_size'],
            inventory_complete=True, consumption_complete=False, daily_rates=[{'food_product_id': product.id, 'daily_references': str(spec['crew_size'] * 12),
                'food_name': product.name, 'reference_unit': 'g', 'reference_quantity': '100', 'quantity': str(spec['crew_size'] * 1200), 'unit': 'g', 'basis': 'stored', 'per_person': False}],
            recorded_at=receipt_at, author_user_id=staff['mission_admin'].id)
        for crew_index in range(spec['crew_size']):
            user = add(session, User, name=f'Tripulante Sintético {index + 1:03d}-{crew_index + 1}',
                       email=f'salus50-{index + 1:03d}-{crew_index + 1}@example.test', hashed_password='!', is_astronaut=True, allergy_screening_completed=True)
            member = add(session, preflight.MissionMember, mission_id=mission.id, user_id=user.id, role='astronaut')
            if crew_index == 1 and index % 6 == 0:
                add(session, clinical_records.HealthOccurrence, astronaut_id=user.id, mission_id=mission.id,
                    condition_name='Rinite alérgica', description='Condição preexistente ficcional.', symptoms='Sintomas sazonais relatados.',
                    start_at=start - timedelta(days=365), recorded_at=min(start - timedelta(days=8), reference - timedelta(days=1)),
                    recorded_by_user_id=doctor.id)
            if crew_index == 0 and index % 4 == 0:
                session.add(medicines.CrewMemberAllergy(crew_member_id=user.id, active_ingredient_id=ingredient.id))
            exam_at = min(start - timedelta(days=4), reference - timedelta(days=2))
            exam = add(session, preflight.AstronautExam, mission_id=mission.id, mission_member_id=member.id, requirement_id=requirement.id,
                       due_at=start - timedelta(days=3), scheduled_at=exam_at)
            result = add(session, preflight.ExamResult, astronaut_exam_id=exam.id, performed_at=exam_at, collected_at=exam_at,
                         recorded_at=exam_at + timedelta(hours=1), recorded_by_user_id=doctor.id, summary='Avaliação ficcional registrada para simulação.')
            add(session, preflight.ExamResultReview, exam_result_id=result.id, reviewer_member_id=session.exec(select(preflight.MissionMember).where(preflight.MissionMember.mission_id == mission.id, preflight.MissionMember.role == 'flight_surgeon')).one().id,
                decision='accepted', reviewed_at=exam_at + timedelta(hours=2))
            add(session, care.NutritionPlan, mission_id=mission.id, mission_member_id=member.id, author_user_id=staff['nutritionist'].id,
                valid_from=exam_at.date(), valid_until=end.date(), dietary_guidance='Plano alimentar ficcional.', energy_target_kcal=2400,
                hydration_target_ml=2500, created_at=exam_at, updated_at=exam_at, updated_by_user_id=staff['nutritionist'].id)
            baseline = {'heart_rate': 62 + rng.randrange(12), 'sleep_duration': 450 + rng.randrange(30), 'fatigue': 2 + crew_index % 2}
            for day in range(-8, days):
                at = start + timedelta(days=day, hours=3)
                if day < 0:
                    at = min(at, reference - timedelta(days=9 - day))
                if at > reference or spec['scenario'] == 'irregular' and day >= 0 and day % 9 != 0:
                    continue
                noise = (-1, 0, 1, 0)[day % 4]
                distance = (at - (cutoff - timedelta(days=7))).total_seconds() / 86400
                shifted = day >= 0 and distance >= 0
                shift = min(1.0, max(0.0, distance / 3))
                scenario = spec['scenario']
                hr = baseline['heart_rate'] + noise * 2
                sleep = baseline['sleep_duration'] + noise * 10
                fatigue = baseline['fatigue'] + noise
                if shifted and scenario in ('progressive', 'paired_outcomes'):
                    hr += 18 * shift
                if shifted and scenario == 'sleep_fatigue':
                    sleep -= round(110 * shift)
                    fatigue += round(5 * shift)
                if scenario == 'isolated' and -3 < distance < -2:
                    hr += 24
                mood = 4 if not shifted or scenario != 'mental_follow_up' else 2
                values = {'heart_rate': hr, 'blood_pressure': (116 + noise * 3 + crew_index, 76 + noise * 2),
                          'respiratory_rate': 15 + noise, 'oxygen_saturation': 98 + noise * 0.3,
                          'body_temperature': 36.6 + noise * 0.1, 'blood_glucose': 90 + crew_index * 3 + noise * 4,
                          'sleep_duration': sleep, 'sleep_quality': 4 + noise, 'fatigue': fatigue, 'mood': mood,
                          'attention': 'worse' if fatigue >= 7 else 'usual', 'consciousness': 'alert'}
                for indicator, value in values.items():
                    observation(session, mission, user, doctor, at, indicator, value, reference=day < 0,
                                delay=2880 if scenario == 'irregular' and day % 2 == 0 else 20)
                if day < 0:
                    continue
                stress = 4 if shifted and scenario == 'mental_follow_up' else 2 + (day % 5 == 0)
                session.add(mental_health.MentalHealthCheckIn(mission_id=mission.id, mission_member_id=member.id,
                    check_in_date=at.date(), happiness_level=mood, satisfaction_level=mood, stress_level=stress,
                    energy_level=3, sleep_quality=3, workload_level=3, isolation_level=2, crew_connection_level=4,
                    created_at=at, updated_at=at + timedelta(minutes=25), updated_by_user_id=user.id))
                if day % 7 == 6:
                    follow_at = at + timedelta(hours=1)
                    session.add(mental_health.PsychologyFollowUp(mission_id=mission.id, mission_member_id=member.id,
                        psychologist_user_id=staff['psychologist'].id, session_at=follow_at,
                        review_period_start=(at - timedelta(days=6)).date(), review_period_end=at.date(),
                        session_summary='Acompanhamento ficcional da semana.', agreed_actions='Revisar rotina com a equipe.',
                        created_at=follow_at, updated_at=follow_at, updated_by_user_id=staff['psychologist'].id))
                for meal_index, meal_type in enumerate(('breakfast', 'lunch', 'dinner')):
                    meal_at = at + timedelta(hours=meal_index * 4)
                    if meal_at > last or meal_at > reference:
                        continue
                    meal = add(session, nutrition.MealLog, mission_id=mission.id, mission_member_id=member.id,
                               consumed_at=meal_at, meal_type=meal_type, recorded_by_user_id=user.id, recorded_at=meal_at + timedelta(minutes=10))
                    item = add(session, nutrition.MealLogItem, meal_log_id=meal.id, food_product_id=product.id, lot_id=lot.id,
                               consumed_quantity=400, consumed_unit='g', consumed_basis='stored', stock_quantity_used=400,
                               product_snapshot=FoodProductResponse.model_validate(product).model_dump(mode='json'),
                               nutrients={'energy_kcal': 800, 'protein_g': 40, 'carbohydrate_g': 100, 'fat_g': 24, 'fiber_g': 12, 'sodium_mg': 720}, revision=1)
                    movement(session, lot, product, user, meal_at + timedelta(minutes=10), -400, item)
                    lot.remaining_quantity -= 400
            if spec['status'] == 'completed':
                outcome_at = end - timedelta(days=1)
                positive = scenario != 'paired_outcomes' or index % 20 == 9
                if positive and scenario in ('progressive', 'sleep_fatigue', 'paired_outcomes', 'mental_follow_up'):
                    occurrence = add(session, clinical_records.HealthOccurrence, astronaut_id=user.id, mission_id=mission.id,
                        condition_name='Fadiga registrada', description='Registro clínico ficcional.', symptoms='Cansaço relatado.',
                        start_at=outcome_at, recorded_at=outcome_at + timedelta(hours=1), recorded_by_user_id=doctor.id,
                        status='recovered', finish_at=end - timedelta(hours=2), resolved_at=end - timedelta(hours=1),
                        resolved_by_user_id=doctor.id, resolution_note='Reavaliação ficcional concluída.')
                    if scenario == 'progressive':
                        add(session, clinical_records.MedicationUse, astronaut_id=user.id, mission_id=mission.id, medicine_id=medicine.id,
                            medicine_name=medicine.name, taken_at=outcome_at + timedelta(hours=2), reason='Registro de simulação', instructed_by=doctor.name,
                            dose='Dose ficcional registrada', occurrence_id=occurrence.id, recorded_by_user_id=doctor.id, recorded_at=outcome_at + timedelta(hours=3))
        if spec['status'] == 'completed':
            add(session, mission_risks.MissionOccurrence, mission_id=mission.id, category='spacecraft' if spec['scenario'] == 'technical_incident' else 'well_being',
                phase='in_flight', event_at=end - timedelta(days=1), recorded_at=end - timedelta(hours=20), confirmed_at=end - timedelta(hours=18),
                confirmed_by_user_id=staff['mission_admin'].id, author_user_id=staff['mission_admin'].id, severity='warning',
                source_references=[{'source': f'synthetic:S50-{index + 1:03d}', 'kind': 'fictional review'}], description='Revisão operacional ficcional.', actions='Inspeção registrada.', outcome='Revisão encerrada.', intervention=False)
        session.add(lot)
        print(f'Generated mission {index + 1}/50', flush=True)
    session.flush()
    return config


def build_manifest(session, reference, mission_registry=None):
    entries = []
    for spec in schedule(reference):
        mission = session.get(preflight.Mission, mission_registry[spec['index']]['id']) if mission_registry else session.exec(select(preflight.Mission).where(preflight.Mission.name == spec['name'])).one()
        member = session.exec(select(preflight.MissionMember).where(preflight.MissionMember.mission_id == mission.id, preflight.MissionMember.role == 'astronaut').order_by(preflight.MissionMember.id)).first()
        scenario = spec['scenario']
        target = {'progressive': ('cardiovascular_resting_heart_rate_shift', 'flight_surgeon_cardiovascular_review'),
                  'paired_outcomes': ('cardiovascular_resting_heart_rate_shift', 'flight_surgeon_cardiovascular_review'),
                  'sleep_fatigue': ('sleep_fatigue_combined', 'rest_period_review'),
                  'mental_follow_up': ('psychological_stress_persistent', 'psychological_support_referral'),
                  'food_supply': ('food_expiration', 'food_inventory_verification')}.get(scenario)
        gap = {'body_composition': 'No longitudinal body composition schema', 'technical_incident': 'No telemetry or maintenance schema'}.get(scenario)
        if spec['status'] == 'planned':
            gap = 'Preflight only; no in-flight follow-up at reference'
        observed = session.exec(select(clinical_records.HealthOccurrence).where(clinical_records.HealthOccurrence.mission_id == mission.id, clinical_records.HealthOccurrence.astronaut_id == member.user_id, clinical_records.HealthOccurrence.recorded_at > spec['cutoff'])).all()
        operational = session.exec(select(mission_risks.MissionOccurrence).where(mission_risks.MissionOccurrence.mission_id == mission.id, mission_risks.MissionOccurrence.confirmed_at > spec['cutoff'])).all()
        records, _ = AstronautDataCollector(session).collect(member.user_id, mission.id, spec['cutoff'])
        entries.append({'case_id': f'S50-C{spec["index"] + 1:03d}', 'mission_id': mission.id, 'astronaut_id': member.user_id,
            'subject_type': 'mission' if scenario == 'food_supply' else 'astronaut', 'scenario': scenario, 'as_of': spec['cutoff'].isoformat(),
            'split': 'evaluation' if spec['index'] >= 30 else 'development', 'expected_risk': target[0] if target else None,
            'expected_action': target[1] if target else None, 'expected_present': bool(target), 'coverage_gap': gap,
            'available_signals': dict(Counter(record.series for record in records)),
            'available_observation_ids': sorted({record.reference[1] for record in records if record.reference[0] == 'health_observations'}),
            'observed_outcome': {'status': 'confirmed' if observed else 'no_recorded_event' if spec['status'] == 'completed' else 'follow_up_incomplete',
                'occurrence_ids': [row.id for row in observed], 'operational_occurrence_ids': [row.id for row in operational],
                'operational_categories': [row.category for row in operational], 'recorded_at': [row.recorded_at.isoformat() for row in observed],
                'follow_up_end': spec['end'].isoformat() if spec['status'] == 'completed' else reference.isoformat()}})
    return entries


def verify(session, mission_ids=None):
    statement = select(preflight.Mission.status, func.count())
    if mission_ids is not None:
        statement = statement.where(preflight.Mission.id.in_(mission_ids))
    counts = dict(session.exec(statement.group_by(preflight.Mission.status)).all())
    if counts != {'completed': 35, 'in_progress': 10, 'planned': 5}:
        raise RuntimeError(f'Unexpected mission counts: {counts}')
    lots = select(nutrition.MissionFoodLot)
    if mission_ids is not None:
        lots = lots.where(nutrition.MissionFoodLot.mission_id.in_(mission_ids))
    for lot in session.exec(lots).all():
        balance = session.exec(select(func.sum(nutrition.FoodStockMovement.quantity)).where(nutrition.FoodStockMovement.lot_id == lot.id)).one()
        if balance != lot.remaining_quantity or balance < 0:
            raise RuntimeError(f'Invalid stock ledger for lot {lot.id}')
    evidence_states = Counter(row.explanation.get('state', 'unknown') for row in session.exec(select(predictive.RecommendationEvent)).all())
    return {'missions': counts, 'evidence_states': dict(evidence_states), 'tables': {table: session.exec(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            for table in ('users', 'mission_members', 'health_observations', 'mental_health_check_ins', 'psychology_follow_ups', 'meal_logs', 'meal_log_items', 'food_stock_movements', 'health_occurrences', 'mission_occurrences', 'knowledge_documents', 'prediction_runs', 'recommendation_events', 'mission_risk_alerts', 'health_notifications')}}


def evaluate(session, entries, evidence=False):
    results = []
    for entry in sorted(entries, key=lambda row: row['as_of']):
        cutoff = datetime.fromisoformat(entry['as_of'])
        mission = session.get(preflight.Mission, entry['mission_id'])
        service = PredictiveService(session, None)
        with patch('app.services.predictive_service.utc_now', return_value=cutoff):
            members = session.exec(select(preflight.MissionMember).where(preflight.MissionMember.mission_id == mission.id, preflight.MissionMember.role == 'astronaut')).all()
            individual_runs = {member.user_id: service.analyze_astronaut(member.user_id, mission.id, trigger='scheduled') for member in members}
            mission_run = service.analyze_mission(mission.id, trigger='scheduled')
            if mission.spacecraft_id:
                service.analyze_spacecraft(mission.spacecraft_id, trigger='scheduled')
        run = mission_run if entry['subject_type'] == 'mission' else individual_runs[entry['astronaut_id']]
        with patch('app.services.mission_risk_service.utc_now', return_value=cutoff):
            admin = session.exec(select(User).join(preflight.MissionMember, preflight.MissionMember.user_id == User.id).where(preflight.MissionMember.mission_id == mission.id, preflight.MissionMember.role == 'mission_admin').order_by(User.id)).first()
            prior = session.exec(select(mission_risks.MissionRiskEvaluation).where(mission_risks.MissionRiskEvaluation.mission_id == mission.id, mission_risks.MissionRiskEvaluation.evaluated_at == cutoff)).first()
            if prior is None:
                MissionRiskService(session, admin).evaluate_internal(mission.id)
        if evidence:
            events = session.exec(select(predictive.RecommendationEvent).join(predictive.RiskPrediction, predictive.RiskPrediction.id == predictive.RecommendationEvent.prediction_id).where(predictive.RiskPrediction.run_id == run.id)).all()
            for event in events:
                prediction = session.get(predictive.RiskPrediction, event.prediction_id)
                action = session.get(predictive.RecommendationAction, event.action_id)
                result = PredictiveKnowledgeService(session).evidence(prediction.model_dump(), action, as_of=cutoff)
                event.sources = result.pop('sources')
                event.explanation = result
                session.add(event)
        predictions = session.exec(select(predictive.RiskPrediction).where(predictive.RiskPrediction.run_id == run.id)).all()
        actions = session.exec(select(predictive.RecommendationAction.code).join(predictive.RecommendationEvent, predictive.RecommendationEvent.action_id == predictive.RecommendationAction.id).join(predictive.RiskPrediction, predictive.RiskPrediction.id == predictive.RecommendationEvent.prediction_id).where(predictive.RiskPrediction.run_id == run.id)).all()
        signals = {row.risk_type for row in predictions if row.prediction_kind != 'insufficient_data'}
        existing_ids = {identifier for prediction in predictions for identifier in prediction.evidence.get('existing_recommendation_ids', [])}
        if existing_ids:
            actions = [*actions, *session.exec(select(predictive.RecommendationAction.code).join(predictive.RecommendationEvent, predictive.RecommendationEvent.action_id == predictive.RecommendationAction.id).where(predictive.RecommendationEvent.id.in_(existing_ids))).all()]
        detected = entry['expected_risk'] in signals if entry['expected_risk'] else bool(signals)
        verdict = 'not_evaluated' if entry['coverage_gap'] else ('true_positive' if detected else 'false_negative') if entry['expected_present'] else ('false_positive' if detected else 'true_negative')
        results.append({'case_id': entry['case_id'], 'run_id': run.id, 'verdict': verdict, 'signals': sorted(signals),
                        'actions': sorted(set(actions)), 'expected_action_found': entry['expected_action'] in actions if entry['expected_action'] else None,
                        'coverage_gap': entry['coverage_gap'], 'outcome_status': entry['observed_outcome']['status']})
    counts = Counter(row['verdict'] for row in results)
    return {'counts': {key: counts[key] for key in ('true_positive', 'true_negative', 'false_positive', 'false_negative', 'not_evaluated')},
            'expected_actions_missing': [row['case_id'] for row in results if row['expected_action_found'] is False and not row['coverage_gap']],
            'cases': results,
            'interpretation': 'Rule-contract confusion matrix, not clinical outcome accuracy. No recorded event does not establish a clinical negative.'}


def publish(args, reference):
    config = configuration(args.seed, reference)
    names = [row['name'] for row in schedule(reference)]
    registry_path = Path('data/synthetic_missions_public/presentation.json')
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else None
    if registry and registry['configuration'] != config:
        raise RuntimeError('Dataset parameters differ from the presentation registry')
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(hashtext(:namespace))'), {'namespace': VERSION + ':public'})
        connection.execute(text('SET LOCAL search_path TO public'))
        with Session(connection, join_transaction_mode='create_savepoint') as session:
            before_ids = set(session.exec(select(preflight.Mission.id)).all())
            existing = session.exec(select(preflight.Mission).where(preflight.Mission.name.in_(names))).all()
            marker = session.exec(select(spacecraft.SpacecraftModule).join(spacecraft.Spacecraft).where(
                spacecraft.Spacecraft.name == 'Salus Synthetic Vessel 01', spacecraft.SpacecraftModule.code == 'M1')).first()
            if registry:
                registered = registry['missions']
                if len(registered) != 50 or any(session.get(preflight.Mission, row['id']) is None or session.get(preflight.Mission, row['id']).name != row['name'] for row in registered):
                    raise RuntimeError('Presentation registry does not match application records')
            elif existing:
                if len(existing) != 50 or marker is None or (marker.technical_specifications or {}).get('dataset') != config:
                    raise RuntimeError('Conflicting or incomplete synthetic dataset in application database')
            else:
                if marker is not None or session.exec(select(User.id).where((User.email.like('salus50-%@example.test')) | (User.email.like('%@crew.salus.example')))).first() is not None:
                    raise RuntimeError('Synthetic account or spacecraft namespace already exists')
                create_dataset(session, args.seed, reference)
            manifest = build_manifest(session, reference, registry['missions'] if registry else None)
            mission_ids = [row['mission_id'] for row in manifest]
            totals = verify(session, mission_ids)
            session.commit()
            report = evaluate(session, manifest, evidence=args.evidence) if args.evaluate else None
            totals = verify(session, mission_ids)
            if not before_ids.issubset(set(session.exec(select(preflight.Mission.id)).all())):
                raise RuntimeError('Preexisting missions were not preserved')
            session.commit()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, payload in (('manifest.json', {'configuration': config, 'cases': manifest}),
                          ('report.json', {'configuration': config, 'schema': 'public', 'totals': totals, 'evaluation': report})):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'schema': 'public', 'synthetic_missions': totals['missions'], 'mission_ids': mission_ids,
                      'preexisting_missions_preserved': len(before_ids - set(mission_ids)),
                      'evaluation': report['counts'] if report else None, 'output': str(output)}, ensure_ascii=False, indent=2))


def run(args):
    if os.getenv('SALUS_SYNTHETIC_ENV') not in ('development', 'test') or any(os.getenv(key, '').lower() in ('prod', 'production') for key in ('APP_ENV', 'ENVIRONMENT', 'ENV')):
        raise RuntimeError('Set SALUS_SYNTHETIC_ENV=development or test on a non-production database')
    if not re.fullmatch(r'salus_synthetic_[a-z0-9_]{1,40}', args.schema):
        raise ValueError('Schema must start with salus_synthetic_ and contain only lowercase letters, digits and underscores')
    reference = datetime.fromisoformat(args.reference)
    if reference.tzinfo is None:
        raise ValueError('Reference requires an explicit UTC offset')
    reference = reference.astimezone(timezone.utc)
    if args.publish:
        return publish(args, reference)
    with engine.begin() as connection:
        connection.execute(text('SELECT pg_advisory_xact_lock(hashtext(:namespace))'), {'namespace': args.schema})
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"'))
    isolated = create_engine(engine.url, connect_args={'options': f'-csearch_path={args.schema}'})
    try:
        with isolated.begin() as connection:
            connection.execute(text('SELECT pg_advisory_xact_lock(hashtext(:namespace))'), {'namespace': args.schema})
            SQLModel.metadata.create_all(connection)
            with Session(connection, join_transaction_mode='create_savepoint') as session:
                for model_type in (knowledge.KnowledgeDocument, knowledge.KnowledgePassage):
                    table = model_type.__tablename__
                    columns = ', '.join(f'"{column.name}"' for column in model_type.__table__.columns)
                    condition = 'WHERE is_public = true' if table == 'knowledge_documents' else 'WHERE document_id IN (SELECT id FROM knowledge_documents)'
                    session.exec(text(f'INSERT INTO "{table}" ({columns}) SELECT {columns} FROM public."{table}" {condition} ON CONFLICT DO NOTHING'))
                definition = connection.execute(text("SELECT pg_get_functiondef('public.salus_cosine_similarity(double precision[], double precision[])'::regprocedure)")).scalar_one()
                session.exec(text(definition.replace('public.salus_cosine_similarity', f'{args.schema}.salus_cosine_similarity')))
                existing = session.exec(select(spacecraft.SpacecraftModule).order_by(spacecraft.SpacecraftModule.id)).first()
                config = configuration(args.seed, reference)
                if existing:
                    if existing.technical_specifications.get('dataset') != config:
                        raise RuntimeError('Dataset parameters differ; select another dedicated schema')
                else:
                    create_dataset(session, args.seed, reference)
                for product in session.exec(select(nutrition.FoodProduct)).all():
                    session.exec(update(nutrition.MealLogItem).where(
                        nutrition.MealLogItem.food_product_id == product.id,
                        nutrition.MealLogItem.product_snapshot['reference_quantity'].as_string().is_(None),
                    ).values(product_snapshot=FoodProductResponse.model_validate(product).model_dump(mode='json')))
                totals = verify(session)
                manifest = build_manifest(session, reference)
                session.commit()
                report = evaluate(session, manifest, evidence=args.evidence) if args.evaluate else None
                totals = verify(session)
                session.commit()
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        for name, payload in (('manifest.json', {'configuration': config, 'cases': manifest}), ('report.json', {'configuration': config, 'schema': args.schema, 'totals': totals, 'evaluation': report})):
            (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'schema': args.schema, 'totals': totals, 'evaluation': report['counts'] if report else None, 'output': str(output)}, ensure_ascii=False, indent=2))
    finally:
        isolated.dispose()


def main():
    parser = argparse.ArgumentParser(description='Generate exactly 50 fictional missions in an isolated development schema')
    parser.add_argument('--seed', type=int, default=50)
    parser.add_argument('--reference', default=DEFAULT_REFERENCE)
    parser.add_argument('--schema', default='salus_synthetic_50')
    parser.add_argument('--output', default='/tmp/salus-synthetic-50')
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--evidence', action='store_true')
    parser.add_argument('--publish', action='store_true', help='Create the synthetic dataset in the application public schema without replacing existing records')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
