from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json

from sqlmodel import select

from app.models.clinical_records import HealthOccurrence, MedicationUse
from app.models.care import NutritionPlan
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert
from app.models.mental_health import MentalHealthCheckIn, PsychologyContactRequest
from app.models.nutrition import MealLog, MealLogItem
from app.models.preflight import Mission, MissionMember
from app.schemas.health import UNITS
from app.services.predictive.features import Measurement, aware


DIRECT_INDICATORS = {
    'respiratory_rate': 'respiratory_rate', 'oxygen_saturation': 'oxygen_saturation', 'body_temperature': 'body_temperature',
    'blood_glucose': 'blood_glucose', 'sleep_duration': 'sleep_duration', 'sleep_quality': 'sleep_quality',
    'fatigue': 'fatigue', 'mood': 'mood',
}
MENTAL_FIELDS = {
    'stress_level': 'mental_stress', 'happiness_level': 'mental_happiness', 'satisfaction_level': 'mental_satisfaction',
    'energy_level': 'mental_energy', 'isolation_level': 'mental_isolation', 'workload_level': 'mental_workload',
    'crew_connection_level': 'mental_crew_connection',
}


def unit_for(indicator, observation):
    return UNITS.get(indicator) or observation.unit


def observation_measurements(observations):
    records = []
    for observation in observations:
        if observation.signal_quality == 'poor':
            continue
        base = dict(at=aware(observation.collected_at), recorded_at=aware(observation.recorded_at), source=observation.source,
                    reference=('health_observations', observation.id), is_preflight_reference=observation.is_preflight_reference,
                    context={'activity': observation.activity, 'signal_quality': observation.signal_quality, 'mission_id': observation.mission_id})
        if observation.indicator == 'heart_rate':
            if observation.activity == 'rest' and observation.value is not None:
                records.append(Measurement(series='resting_heart_rate', value=float(observation.value), unit='bpm', **base))
        elif observation.indicator == 'blood_pressure':
            records.append(Measurement(series='systolic_pressure', value=float(observation.systolic), unit='mmHg', **base))
            records.append(Measurement(series='diastolic_pressure', value=float(observation.diastolic), unit='mmHg', **base))
        elif observation.indicator in DIRECT_INDICATORS and observation.value is not None:
            records.append(Measurement(series=DIRECT_INDICATORS[observation.indicator], value=float(observation.value),
                                       unit=unit_for(observation.indicator, observation), **base))
    return records


def check_in_measurements(check_ins):
    records = []
    for check_in in check_ins:
        for field, series in MENTAL_FIELDS.items():
            value = getattr(check_in, field)
            if value is None:
                continue
            records.append(Measurement(series=series, value=float(value), at=aware(check_in.created_at), recorded_at=aware(check_in.updated_at),
                                       unit='1-5', source='self_report', reference=('mental_health_check_ins', check_in.id)))
    return records


def daily_intake_measurements(meals, items_by_meal):
    totals = defaultdict(lambda: {'energy_kcal': 0.0, 'protein_g': 0.0, 'energy_known': False, 'protein_known': False, 'recorded_at': None, 'meal_ids': []})
    for meal in meals:
        day = aware(meal.consumed_at).date()
        bucket = totals[day]
        bucket['meal_ids'].append(meal.id)
        recorded = aware(meal.recorded_at)
        bucket['recorded_at'] = recorded if bucket['recorded_at'] is None or recorded > bucket['recorded_at'] else bucket['recorded_at']
        for item in items_by_meal.get(meal.id, []):
            for nutrient, key in (('energy_kcal', 'energy_known'), ('protein_g', 'protein_known')):
                value = item.nutrients.get(nutrient)
                if value is not None:
                    bucket[nutrient] += float(value)
                    bucket[key] = True
    records = []
    for day, bucket in totals.items():
        closes_at = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)
        recorded_at = max(bucket['recorded_at'], closes_at)
        reference = ('meal_days', int(day.strftime('%Y%m%d')))
        if bucket['energy_known']:
            records.append(Measurement(series='energy_intake', value=bucket['energy_kcal'], at=closes_at, recorded_at=recorded_at, unit='kcal/day', source='meal_log', reference=reference))
        if bucket['protein_known']:
            records.append(Measurement(series='protein_intake', value=bucket['protein_g'], at=closes_at, recorded_at=recorded_at, unit='g/day', source='meal_log', reference=reference))
    return records


class AstronautDataCollector:
    def __init__(self, session):
        self.session = session

    def memberships(self, astronaut_id):
        return self.session.exec(select(MissionMember).where(MissionMember.user_id == astronaut_id, MissionMember.role == 'astronaut')).all()

    def collect(self, astronaut_id, mission_id, as_of):
        as_of = aware(as_of)
        members = self.memberships(astronaut_id)
        member_ids = [member.id for member in members]
        observations = self.session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == astronaut_id, HealthObservation.collected_at <= as_of, HealthObservation.recorded_at <= as_of).order_by(HealthObservation.collected_at, HealthObservation.id)).all()
        records = observation_measurements(observations)
        check_ins = self.session.exec(select(MentalHealthCheckIn).where(MentalHealthCheckIn.mission_member_id.in_(member_ids), MentalHealthCheckIn.updated_at <= as_of)).all() if member_ids else []
        records.extend(check_in_measurements(check_ins))
        meals = self.session.exec(select(MealLog).where(MealLog.mission_member_id.in_(member_ids), MealLog.is_deleted == False, MealLog.recorded_at <= as_of, MealLog.consumed_at <= as_of)).all() if member_ids else []
        items = self.session.exec(select(MealLogItem).where(MealLogItem.meal_log_id.in_([meal.id for meal in meals]), MealLogItem.is_active == True)).all() if meals else []
        items_by_meal = defaultdict(list)
        for item in items:
            items_by_meal[item.meal_log_id].append(item)
        records.extend(daily_intake_measurements(meals, items_by_meal))
        context = self.context(astronaut_id, mission_id, members, observations, meals, as_of)
        return records, context

    def context(self, astronaut_id, mission_id, members, observations, meals, as_of):
        week = as_of - timedelta(days=7)
        recent = [row for row in observations if aware(row.collected_at) > week and row.symptoms_status != 'unknown']
        symptoms = None if not recent else any(row.symptoms_status == 'present' for row in recent)
        alerts = self.session.exec(select(HealthAlert).where(HealthAlert.astronaut_id == astronaut_id, HealthAlert.created_at <= as_of)).all()
        active_alerts = [{'id': alert.id, 'rule_id': alert.rule_id, 'indicator': alert.indicator, 'severity': alert.severity}
                         for alert in alerts if alert.resolved_at is None or aware(alert.resolved_at) > as_of]
        occurrences = self.session.exec(select(HealthOccurrence).where(HealthOccurrence.astronaut_id == astronaut_id, HealthOccurrence.start_at <= as_of, HealthOccurrence.recorded_at <= as_of)).all()
        active_occurrences = [{'id': row.id, 'icd_code': row.icd_code} for row in occurrences if row.finish_at is None or aware(row.finish_at) > as_of]
        medications = self.session.exec(select(MedicationUse).where(MedicationUse.astronaut_id == astronaut_id, MedicationUse.taken_at <= as_of, MedicationUse.taken_at > week, MedicationUse.recorded_at <= as_of)).all()
        mission = self.session.get(Mission, mission_id) if mission_id else None
        member = next((row for row in members if row.mission_id == mission_id), None)
        pending_psychology = bool(member and self.session.exec(select(PsychologyContactRequest).where(PsychologyContactRequest.mission_member_id == member.id, PsychologyContactRequest.status == 'pending', PsychologyContactRequest.created_at <= as_of)).first())
        return {
            'symptoms_reported_7d': symptoms, 'active_clinical_alerts': active_alerts,
            'active_health_occurrences': len(active_occurrences), 'medication_uses_7d': len(medications),
            'mission_id': mission_id, 'mission_status': mission_status_at(mission, as_of),
            'pending_psychology_request': pending_psychology,
            'nutrition_plan': self.nutrition_context(member, meals, as_of) if member else None,
        }

    def nutrition_context(self, member, meals, as_of):
        today = as_of.date()
        plan = self.session.exec(select(NutritionPlan).where(NutritionPlan.mission_member_id == member.id, NutritionPlan.valid_from <= today, NutritionPlan.created_at <= as_of).order_by(NutritionPlan.valid_from.desc(), NutritionPlan.id.desc())).first()
        if plan is None or plan.valid_until is not None and plan.valid_until < today or plan.energy_target_kcal is None:
            return None
        days = {today - timedelta(days=offset) for offset in range(1, 8)}
        member_meals = [meal for meal in meals if meal.mission_member_id == member.id and aware(meal.consumed_at).date() in days]
        covered = sorted({aware(meal.consumed_at).date() for meal in member_meals})
        if not covered:
            return {'plan_id': plan.id, 'energy_target_kcal': plan.energy_target_kcal, 'covered_days': 0, 'mean_daily_energy_kcal': None}
        items = self.session.exec(select(MealLogItem).where(MealLogItem.meal_log_id.in_([meal.id for meal in member_meals]), MealLogItem.is_active == True)).all()
        total = sum(float(item.nutrients['energy_kcal']) for item in items if item.nutrients.get('energy_kcal') is not None)
        return {'plan_id': plan.id, 'energy_target_kcal': plan.energy_target_kcal, 'covered_days': len(covered), 'mean_daily_energy_kcal': total / len(covered)}


def fingerprint(records, context):
    payload = sorted((record.series, list(record.reference or ()), record.value, aware(record.recorded_at).isoformat()) for record in records)
    stable_context = {key: value for key, value in context.items() if key != 'nutrition_plan'}
    stable_context['nutrition_plan'] = context.get('nutrition_plan')
    return sha256(json.dumps([payload, stable_context], sort_keys=True, default=str).encode()).hexdigest()


def mission_status_at(mission, as_of):
    if mission is None:
        return None
    if mission.started_at is None or aware(mission.started_at) > aware(as_of):
        return 'planned'
    if mission.ended_at is not None and aware(mission.ended_at) <= aware(as_of):
        return 'completed'
    return 'in_progress'
