"""Add fictional demo accounts and scenarios without changing existing records."""
import argparse
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, text
from sqlmodel import Session, select

import app.models.health
import app.models.knowledge
import app.models.revoked_token
from app.database import engine
from app.models.health import HealthObservation
from app.models.preflight import AstronautExam, ExamResult, ExamType, Mission, MissionMember
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.schemas.preflight import (
    ExamTypeCreate, MemberCreate, MissionCreate, RequirementCreate,
    ResultCreate, ReviewCreate, SchedulePatch,
)
from app.schemas.users import UserCreate
from app.services.health_service import HealthService
from app.services.preflight_service import PreflightService
from app.services.user_service import UserService

EMAIL = 'demo.monitoramento@example.com'
PASSWORD = 'Monitoramento2026!'
NOTE = 'DEMO: dados fictícios, sem validade clínica.'


def inventory(session):
    print('\nTables and record counts:')
    quote = engine.dialect.identifier_preparer.quote
    for name in sorted(inspect(engine).get_table_names()):
        count = session.exec(text(f'SELECT count(*) FROM {quote(name)}')).scalar_one()
        print(f'  {name}: {count}')


def seed():
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with Session(engine) as session:
        inventory(session)
        users = []
        for name, email, astronaut, physician in (
            ('Demo Monitoramento', EMAIL, True, True),
            ('Astronauta Fictícia Demo', 'tripulante.monitoramento@example.com', True, False),
            ('Médica Fictícia Demo', 'medica.monitoramento@example.com', False, True),
            ('Coordenação Fictícia Demo', 'coordenacao.monitoramento@example.com', False, True),
        ):
            user = session.exec(select(User).where(User.email == email)).first()
            if user is None:
                user = UserService(session).create_user(UserCreate(
                    name=name, email=email, password=PASSWORD, password_confirmation=PASSWORD,
                    is_astronaut=astronaut, is_physician=physician,
                ))
            elif (user.is_astronaut, user.is_physician) != (astronaut, physician):
                raise RuntimeError(f'Account {email} already exists with other profiles; no profile was changed.')
            users.append(user)
        demo, astronaut, doctor, coordinator = users
        for label, owner, surgeon, target in (
            ('Administração', demo, doctor, astronaut),
            ('Atendimento médico', doctor, demo, astronaut),
            ('Meu monitoramento', coordinator, doctor, demo),
        ):
            name = f'DEMO · {label} · dados fictícios'
            mission = session.exec(select(Mission).where(Mission.name == name)).first()
            admin = PreflightService(session, owner)
            if mission is None:
                mission = admin.create_mission(MissionCreate(
                    name=name, planned_launch_at=now+timedelta(days=15),
                ))
            admin.create_member(mission.id, MemberCreate(user_id=surgeon.id, role='flight_surgeon'))
            member = admin.create_member(mission.id, MemberCreate(user_id=target.id, role='astronaut'))
            clinical = PreflightService(session, surgeon)
            for index, title in enumerate(('Cardiovascular', 'Visão', 'Respiração', 'Sono', 'Avaliação geral')):
                code = f'demo_monitoramento_{index}'
                exam_type = session.exec(select(ExamType).where(ExamType.code == code)).first()
                if exam_type is None:
                    exam_type = admin.create_exam_type(ExamTypeCreate(code=code, name=f'DEMO · {title}', description=NOTE))
                requirement = clinical.create_requirement(mission.id, RequirementCreate(
                    exam_type_id=exam_type.id, due_days_before_launch=5+index,
                ))
                exam = session.exec(select(AstronautExam).where(
                    AstronautExam.mission_member_id == member.id,
                    AstronautExam.requirement_id == requirement.id,
                )).one()
                # Keep existing scenarios intact on repeated executions.
                if index == 1 and exam.scheduled_at is None:
                    clinical.schedule(mission.id, exam.id, SchedulePatch(scheduled_at=now+timedelta(days=2)))
                if index >= 2 and not session.exec(select(ExamResult).where(ExamResult.astronaut_exam_id == exam.id)).first():
                    result = clinical.create_result(mission.id, exam.id, ResultCreate(
                        performed_at=now-timedelta(days=1), summary=f'{NOTE} Avaliação simulada de {title.lower()}.',
                    ))
                    if index >= 3:
                        clinical.create_review(mission.id, result.id, ReviewCreate(
                            decision='repeat_requested' if index == 3 else 'accepted', notes=NOTE,
                        ))
            health = HealthService(session, surgeon)
            for day in range(30):
                collected = now-timedelta(days=day, minutes=10)
                for indicator, value in (
                    ('heart_rate', round(72+6*math.sin(day), 0)),
                    ('blood_pressure', None), ('respiratory_rate', 16),
                    ('oxygen_saturation', 98), ('body_temperature', 36.6),
                    ('consciousness', None), ('sleep_duration', 440+day%4*10),
                    ('sleep_quality', 3+day%3), ('fatigue', 2+day%5),
                    ('mood', 3+day%3), ('attention', None),
                ):
                    marker = f'{NOTE} série {indicator}, amostra {day}.'
                    exists = session.exec(select(HealthObservation).where(
                        HealthObservation.astronaut_id == target.id,
                        HealthObservation.mission_id == mission.id,
                        HealthObservation.note == marker,
                    )).first()
                    if exists:
                        continue
                    body = dict(indicator=indicator, mission_id=mission.id, collected_at=collected,
                                source='manual_measurement', note=marker, is_preflight_reference=day == 29)
                    if indicator == 'blood_pressure':
                        body.update(systolic=118+day%8, diastolic=76+day%5)
                    elif indicator in ('consciousness', 'attention'):
                        body['category'] = 'alert' if indicator == 'consciousness' else 'usual'
                    else:
                        body['value'] = value
                    health.create(target.id, ObservationCreate(**body))
            states = clinical.checklist(mission.id, member.id, 1, 100)['data']
            assert {row.state for row in states} == {'pending', 'scheduled', 'awaiting_review', 'repeat_requested', 'completed'}
            assert len(health.summary(target.id, mission.id).indicators) == 11
            print(f'Mission {mission.id}: {label}; five checklist states and eleven indicators verified.')
        inventory(session)
        print(f'\nLogin: {EMAIL}\nInitial password for new accounts: {PASSWORD}')
        print('Existing accounts keep their passwords. No previous data was removed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Add fictional data to the configured database')
    args = parser.parse_args()
    if args.apply:
        seed()
    else:
        with Session(engine) as session:
            inventory(session)
        print('Use --apply to add the demonstration.')
