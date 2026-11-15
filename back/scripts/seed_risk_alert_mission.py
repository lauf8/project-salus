import json
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import engine
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlert, HealthAlertSettings
from app.models.mission_risks import MissionRiskAlert, MissionRiskPlan
from app.models.nutrition import FoodProduct, MealLog, MissionFoodLot
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.schemas.mission_risks import RiskPlanInput
from app.schemas.nutrition import FoodLotCreate, FoodProductInput, MealCreate
from app.schemas.preflight import MemberCreate, MissionCreate
from app.services.health_service import HealthService
from app.services.mission_risk_service import MissionRiskService
from app.services.nutrition_service import NutritionService
from app.services.preflight_service import PreflightService


MISSION_NAME = 'Salus Alert Demonstration — Synthetic Data'
PEOPLE = {
    'admin': ('Salus Demo Mission Admin', 'alerts-demo-admin@salus.example', 'is_mission_admin'),
    'physician': ('Salus Demo Physician', 'alerts-demo-physician@salus.example', 'is_physician'),
    'astronaut_1': ('Salus Demo Astronaut 1', 'alerts-demo-astronaut-1@salus.example', 'is_astronaut'),
    'astronaut_2': ('Salus Demo Astronaut 2', 'alerts-demo-astronaut-2@salus.example', 'is_astronaut'),
}


def seed_alert_mission(session):
    now = datetime.now(timezone.utc)
    people = {}
    for key, (name, email, profile) in PEOPLE.items():
        user = session.exec(select(User).where(User.email == email)).first()
        if user is not None and (user.name != name or not user.is_active or not getattr(user, profile)):
            raise RuntimeError('An existing account conflicts with the synthetic fixture; no account will be overwritten')
        if user is None:
            user = User(name=name, email=email, hashed_password='!synthetic-public-demo', **{profile: True})
            session.add(user)
            session.commit()
            session.refresh(user)
        people[key] = user
    admin, doctor = people['admin'], people['physician']
    preflight = PreflightService(session, admin)
    mission = session.exec(select(Mission).where(Mission.name == MISSION_NAME)).first()
    if mission is None:
        mission = preflight.create_mission(MissionCreate(name=MISSION_NAME, crew_size=2,
            planned_launch_at=now - timedelta(days=3), started_at=now - timedelta(days=3),
            astronaut_ids=[people['astronaut_1'].id, people['astronaut_2'].id]))
    members = session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id)).all()
    if any(member.user_id not in {person.id for person in people.values()} for member in members):
        raise RuntimeError('The fixture mission contains unrelated members; it will not be modified')
    doctor_member = next((member for member in members if member.user_id == doctor.id), None)
    if doctor_member is None:
        preflight.create_member(mission.id, MemberCreate(user_id=doctor.id, role='flight_surgeon'))
    elif doctor_member.role != 'flight_surgeon':
        raise RuntimeError('The fixture physician role was changed; it will not be overwritten')
    settings = session.get(HealthAlertSettings, mission.id)
    if settings is None:
        session.add(HealthAlertSettings(mission_id=mission.id, profile_id='simulation-v2', timezone='UTC',
            emergency_channel='Synthetic exercise — Salus Demo Physician; no external dispatch',
            approval_note='Synthetic demonstration only; not a clinical validation or a real patient record.',
            approved_by_user_id=doctor.id))
        session.commit()
    scenarios = [
        ('astronaut_1', 'blood_glucose', 53),
        ('astronaut_1', 'oxygen_saturation', 91),
        ('astronaut_2', 'body_temperature', 39.4),
        ('astronaut_2', 'heart_rate', 118),
    ]
    for key, indicator, value in scenarios:
        astronaut = people[key]
        request_id = str(uuid5(NAMESPACE_URL, f'salus-alert-demo:{mission.id}:{astronaut.id}:{indicator}'))
        existing = session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == astronaut.id, HealthObservation.client_request_id == request_id)).first()
        if existing is None:
            HealthService(session, doctor).create(astronaut.id, ObservationCreate(
                mission_id=mission.id, indicator=indicator, value=value, collected_at=now - timedelta(minutes=2),
                source='manual_measurement', activity='rest', signal_quality='good', symptoms_status='unknown',
                glucose_context='fasting' if indicator == 'blood_glucose' else 'unknown',
                client_request_id=request_id,
                note='SYNTHETIC EXERCISE: fictional person and measurement for demonstrating clinical alerts. No real disease diagnosis.',
            ))
    nutrition = NutritionService(session, doctor)
    food = session.exec(select(FoodProduct).where(FoodProduct.name == 'Salus Demo — Rice portions')).first()
    if food is None:
        food = nutrition.save_product(FoodProductInput(name='Salus Demo — Rice portions', category='food',
            preservation_method='thermostabilized', physical_form='solid', reference_quantity=100,
            reference_unit='g', reference_basis='stored', preparation_method='ready_to_consume'))
    lot = session.exec(select(MissionFoodLot).where(MissionFoodLot.mission_id == mission.id, MissionFoodLot.lot_code == 'SALUS-ALERT-DEMO-FOOD')).first()
    if lot is None:
        lot = nutrition.create_lot(mission.id, FoodLotCreate(food_product_id=food.id, lot_code='SALUS-ALERT-DEMO-FOOD',
            expiration_date=(now + timedelta(days=12)).date(), initial_quantity=600, stock_unit='g'))
    meal_id = str(uuid5(NAMESPACE_URL, f'salus-alert-demo-meal:{mission.id}'))
    if session.exec(select(MealLog).where(MealLog.mission_id == mission.id, MealLog.client_request_id == meal_id)).first() is None:
        member = session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id, MissionMember.user_id == people['astronaut_1'].id)).one()
        nutrition.create_meal(mission.id, MealCreate(mission_member_id=member.id, consumed_at=now - timedelta(minutes=1),
            meal_type='lunch', client_request_id=meal_id, notes='Synthetic inventory exercise meal.',
            items=[{'food_product_id': food.id, 'lot_id': lot.id, 'consumed_quantity': 100, 'consumed_unit': 'g', 'consumed_basis': 'stored'}]))
    risk = MissionRiskService(session, doctor)
    if session.exec(select(MissionRiskPlan).where(MissionRiskPlan.mission_id == mission.id)).first() is None:
        risk.save_plan(mission.id, RiskPlanInput(exposure_start_at=mission.started_at,
            planned_end_at=now + timedelta(days=8), crew_size=2, inventory_complete=True,
            daily_rates=[{'food_product_id': food.id, 'quantity': 100, 'unit': 'g', 'per_person': True}],
            approved_actions=[{'food_product_id': food.id,
                'action': 'Synthetic exercise: verify usable rice portions and coordinate replenishment with mission control.',
                'source_reference': 'Synthetic exercise plan; operational stock verification only, not clinical advice.'}]))
    health_alerts = session.exec(select(HealthAlert).where(HealthAlert.mission_id == mission.id, HealthAlert.status != 'resolved')).all()
    food_alerts = session.exec(select(MissionRiskAlert).where(MissionRiskAlert.mission_id == mission.id, MissionRiskAlert.status != 'resolved')).all()
    return {'mission_id': mission.id, 'mission_name': mission.name, 'synthetic_data': True,
            'physician': {'id': doctor.id, 'name': doctor.name},
            'astronauts': [{'id': people[key].id, 'name': people[key].name} for key in ('astronaut_1', 'astronaut_2')],
            'clinical_alerts': [{'id': alert.id, 'indicator': alert.indicator, 'severity': alert.severity} for alert in health_alerts],
            'food_alerts': [{'id': alert.id, 'severity': alert.severity} for alert in food_alerts]}


def main():
    with engine.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(742306103)'))
        try:
            with Session(engine) as session:
                print(json.dumps(seed_alert_mission(session), ensure_ascii=False))
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(742306103)'))


if __name__ == '__main__':
    main()
