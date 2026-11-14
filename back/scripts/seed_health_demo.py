import math
import os
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.database import engine
from app.models.health import HealthObservation
from app.models.preflight import Mission
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.schemas.preflight import MemberCreate, MissionCreate
from app.schemas.users import UserCreate
from app.services.health_service import HealthService
from app.services.preflight_service import PreflightService
from app.services.user_service import UserService


PASSWORD = 'NasaDemo2026!'
MISSION_NAME = 'Missão demonstração · dados fictícios'


def seed():
    database = os.environ.get('PGDATABASE', '')
    if not any(marker in database.lower() for marker in ('validation', 'demo', 'test')):
        raise RuntimeError('Demo seeding requires a dedicated validation, demo or test database')
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with Session(engine) as session:
        people = {}
        for name, email, astronaut, physician in (
            ('Astronauta Demo', 'astronauta.demo@example.com', True, False),
            ('Médica Demo', 'medica.demo@example.com', False, True),
            ('Coordenação Demo', 'coordenacao.demo@example.com', False, True),
        ):
            user = session.exec(select(User).where(User.email == email)).first()
            if user is None:
                user = UserService(session).create_user(UserCreate(
                    name=name, email=email, password=PASSWORD, password_confirmation=PASSWORD,
                    is_astronaut=astronaut, is_physician=physician,
                ))
            people[email] = user
        astronaut = people['astronauta.demo@example.com']
        doctor = people['medica.demo@example.com']
        admin = people['coordenacao.demo@example.com']
        preflight = PreflightService(session, admin)
        mission = session.exec(select(Mission).where(Mission.name == MISSION_NAME)).first()
        if mission is None:
            mission = preflight.create_mission(MissionCreate(
                name=MISSION_NAME, planned_launch_at=now-timedelta(days=10), started_at=now-timedelta(days=10),
            ))
        preflight.create_member(mission.id, MemberCreate(user_id=doctor.id, role='flight_surgeon'))
        preflight.create_member(mission.id, MemberCreate(user_id=astronaut.id, role='astronaut'))
        existing = session.exec(select(HealthObservation).where(
            HealthObservation.astronaut_id == astronaut.id,
            HealthObservation.note == 'Dados fictícios para demonstração do painel.',
        )).all()
        if existing:
            print(f'Demo already contains {len(existing)} observations for astronaut {astronaut.id}')
            return
        ranges = {
            'heart_rate': lambda step: round(72+7*math.sin(step/3), 0),
            'blood_pressure': lambda step: (round(119+5*math.sin(step/4)), round(78+4*math.cos(step/4))),
            'respiratory_rate': lambda step: round(16+2*math.sin(step/5), 0),
            'oxygen_saturation': lambda step: round(98+math.sin(step/4), 1),
            'body_temperature': lambda step: round(36.6+0.2*math.sin(step/6), 1),
            'consciousness': lambda step: 'alert',
            'sleep_duration': lambda step: 435+int(45*math.sin(step/3)),
            'sleep_quality': lambda step: 3+step%3,
            'fatigue': lambda step: 2+step%5,
            'mood': lambda step: 3+step%3,
            'attention': lambda step: ('usual', 'better', 'usual', 'worse')[step%4],
        }
        created = 0
        for indicator, calculate in ranges.items():
            baseline_time = mission.started_at-timedelta(days=3)
            baseline_value = calculate(0)
            payload = {
                'indicator': indicator, 'mission_id': mission.id,
                'collected_at': baseline_time, 'source': 'manual_measurement',
                'is_preflight_reference': True, 'note': 'Dados fictícios para demonstração do painel.',
            }
            if indicator == 'blood_pressure':
                payload.update(systolic=baseline_value[0], diastolic=baseline_value[1])
            elif indicator in ('consciousness', 'attention'):
                payload['category'] = baseline_value
            else:
                payload['value'] = baseline_value
            HealthService(session, doctor).create(astronaut.id, ObservationCreate(**payload))
            created += 1
            daily = indicator in ('sleep_duration', 'sleep_quality', 'mood', 'fatigue', 'attention', 'consciousness')
            timestamps = [now-timedelta(days=day, hours=1) for day in range(29, -1, -1) if day not in (8, 17, 23)]
            if not daily:
                timestamps = [time for time in timestamps if time < now-timedelta(days=7)]
                timestamps += [now-timedelta(hours=hour+1) for hour in range(7*24, -1, -4) if hour not in (48, 52, 108, 112)]
            for step, collected_at in enumerate(timestamps):
                value = calculate(step)
                body = {
                    'indicator': indicator, 'mission_id': mission.id, 'collected_at': collected_at,
                    'source': 'manual_measurement' if indicator in ('heart_rate', 'blood_pressure', 'respiratory_rate', 'oxygen_saturation', 'body_temperature', 'consciousness') else 'self_report',
                    'note': 'Dados fictícios para demonstração do painel.',
                }
                if indicator == 'blood_pressure':
                    body.update(systolic=value[0], diastolic=value[1])
                elif indicator in ('consciousness', 'attention'):
                    body['category'] = value
                elif indicator == 'sleep_duration':
                    body['sleep_ended_at'] = collected_at-timedelta(minutes=30)
                    body['sleep_started_at'] = body['sleep_ended_at']-timedelta(minutes=value)
                else:
                    body['value'] = value
                recorder = doctor if indicator == 'consciousness' else astronaut
                HealthService(session, recorder).create(astronaut.id, ObservationCreate(**body))
                created += 1
        print(f'Created {created} fictional observations; astronaut_id={astronaut.id}; mission_id={mission.id}')
        print('Astronaut: astronauta.demo@example.com')
        print('Physician: medica.demo@example.com')
        print('Password: NasaDemo2026!')


if __name__ == '__main__':
    seed()
