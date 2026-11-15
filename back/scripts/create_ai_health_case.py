import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import engine
from app.models.clinical_records import ClinicalAssessment
from app.models.health_alerts import HealthAlert
from app.models.mission_risks import MissionRiskPlan
from app.models.notifications import HealthNotification
from app.models.predictive import RecommendationEvent
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.health import ObservationCreate
from app.schemas.preflight import MemberCreate, MissionPatch
from app.services.clinical_record_service import ClinicalRecordService
from app.services.health_service import HealthService
from app.services.predictive.features import aware
from app.services.predictive_service import PredictiveService
from app.services.preflight_service import PreflightService

EMAIL = 'matheus.valenca@crew.salus.example'


def readings(start, reference):
    rows = []
    for offset in range(7, 2, -1):
        at = start - timedelta(days=offset)
        variation = (offset % 3) - 1
        for indicator, value in (('heart_rate', 68 + variation * 2), ('respiratory_rate', 15 + variation),
                                 ('oxygen_saturation', 98 + variation * 0.3), ('body_temperature', 36.6 + variation * 0.1),
                                 ('sleep_duration', 465 + variation * 15), ('fatigue', 2 + variation)):
            rows.append((at, indicator, value, True, []))
    for day in range(12, 0, -1):
        at = reference - timedelta(days=day)
        shift = max(0, 7 - day) / 6
        for indicator, value in (('heart_rate', 68 + (day % 3 - 1) * 2 + 26 * shift),
                                 ('respiratory_rate', 15 + 7 * shift), ('oxygen_saturation', 98 - 4 * shift),
                                 ('body_temperature', 36.6 + 1.1 * shift), ('sleep_duration', 465 - round(120 * shift)),
                                 ('fatigue', 2 + round(5 * shift))):
            rows.append((at, indicator, round(value, 2), False, ['fatigue'] if day <= 3 else []))
    for minutes, pulse, breathing, oxygen, temperature in ((20, 112, 25, 92, 38.3), (2, 118, 28, 90, 38.7)):
        at = reference - timedelta(minutes=minutes)
        for indicator, value in (('heart_rate', pulse), ('respiratory_rate', breathing), ('oxygen_saturation', oxygen), ('body_temperature', temperature)):
            rows.append((at, indicator, value, False, ['shortness_of_breath', 'fatigue']))
    return rows


def create_case(path):
    if os.getenv('SALUS_SYNTHETIC_ENV') not in ('development', 'test') or any(os.getenv(key, '').lower() in ('prod', 'production') for key in ('APP_ENV', 'ENVIRONMENT', 'ENV')):
        raise RuntimeError('Only development and test databases are supported')
    metadata = json.loads(path.read_text()) if path.exists() else None
    reference = datetime.fromisoformat(metadata['reference']) if metadata else datetime.now(timezone.utc).replace(microsecond=0)
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('salus-ai-health-case'))"))
        with Session(connection, join_transaction_mode='create_savepoint') as session:
            mission = session.exec(select(Mission).where(Mission.name == 'Atlântico 03')).one()
            if mission.status != 'in_progress' or mission.started_at is None:
                raise RuntimeError('The selected mission must be in progress')
            doctor = session.exec(select(User).join(MissionMember, MissionMember.user_id == User.id).where(
                MissionMember.mission_id == mission.id, MissionMember.role == 'flight_surgeon', User.is_physician == True)).one()
            admin = session.exec(select(User).join(MissionMember, MissionMember.user_id == User.id).where(
                MissionMember.mission_id == mission.id, MissionMember.role == 'mission_admin')).one()
            person = session.exec(select(User).where(User.email == EMAIL)).first()
            if person is not None and (person.name != 'Matheus Valença' or not person.is_astronaut):
                raise RuntimeError('An existing account conflicts with the requested case')
            if person is None:
                person = User(name='Matheus Valença', email=EMAIL, hashed_password='!', is_astronaut=True, allergy_screening_completed=True)
                session.add(person)
                session.flush()
                crew_count = len(session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id, MissionMember.role == 'astronaut')).all())
                preflight = PreflightService(session, admin)
                if mission.crew_size is None or mission.crew_size < crew_count + 1:
                    preflight.update_mission(mission.id, MissionPatch(crew_size=crew_count + 1))
                preflight.create_member(mission.id, MemberCreate(user_id=person.id, role='astronaut'))
                plan = session.exec(select(MissionRiskPlan).where(MissionRiskPlan.mission_id == mission.id).order_by(MissionRiskPlan.recorded_at.desc(), MissionRiskPlan.id.desc())).first()
                if plan is not None and plan.crew_size != crew_count + 1:
                    values = plan.model_dump(exclude={'id', 'recorded_at'})
                    factor = (crew_count + 1) / plan.crew_size
                    values['crew_size'] = crew_count + 1
                    values['author_user_id'] = admin.id
                    values['daily_rates'] = [{**rate, 'daily_references': str(float(rate['daily_references']) * factor),
                        'quantity': str(float(rate['quantity']) * factor)} for rate in plan.daily_rates]
                    session.add(MissionRiskPlan(**values))
                    session.flush()
                health = HealthService(session, doctor)
                for at, indicator, value, baseline, symptoms in readings(aware(mission.started_at), reference):
                    health.create(person.id, ObservationCreate(mission_id=mission.id, indicator=indicator, value=value,
                        collected_at=at, source='self_report' if indicator in ('sleep_duration', 'fatigue') else 'manual_measurement',
                        activity='rest', signal_quality='good', supplemental_oxygen=False,
                        symptoms_status='present' if symptoms else 'absent', symptoms=symptoms,
                        is_preflight_reference=baseline, note='Coleta em repouso registrada pela equipe de saúde.',
                        client_request_id=uuid5(NAMESPACE_URL, f'{EMAIL}:{at.isoformat()}:{indicator}')))
            elif session.exec(select(MissionMember).where(MissionMember.mission_id == mission.id, MissionMember.user_id == person.id, MissionMember.role == 'astronaut')).first() is None:
                raise RuntimeError('The existing account is not assigned to the selected mission')
            metadata = {'origin': 'fictional development case with real application services and real Ollama generation',
                        'reference': reference.isoformat(), 'astronaut_id': person.id, 'astronaut_name': person.name,
                        'mission_id': mission.id, 'mission_name': mission.name, 'physician_id': doctor.id, 'physician_name': doctor.name}
            session.commit()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    return metadata


def generate_case(metadata, path):
    with Session(engine) as session:
        doctor = session.get(User, metadata['physician_id'])
        person_id, mission_id = metadata['astronaut_id'], metadata['mission_id']
        predictive = PredictiveService(session, doctor)
        run = predictive.analyze_astronaut(person_id, mission_id, trigger='scheduled')
        events = session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == 'astronaut', RecommendationEvent.subject_id == person_id,
            RecommendationEvent.mission_id == mission_id, RecommendationEvent.status == 'pending')).all()
        for event in events:
            if not event.explanation.get('generated'):
                predictive.fill_evidence(event)
                session.commit()
        assessment = session.exec(select(ClinicalAssessment).where(ClinicalAssessment.astronaut_id == person_id, ClinicalAssessment.mission_id == mission_id).order_by(ClinicalAssessment.id.desc())).first()
        if assessment is None or assessment.report.get('generation_status') != 'completed':
            assessment = ClinicalRecordService(session, doctor).create_assessment(person_id, mission_id)
        alerts = session.exec(select(HealthAlert).where(HealthAlert.astronaut_id == person_id, HealthAlert.mission_id == mission_id, HealthAlert.status != 'resolved')).all()
        notifications = session.exec(select(HealthNotification).where(HealthNotification.mission_id == mission_id, HealthNotification.recipient_user_id == doctor.id,
            HealthNotification.alert_id.in_([row.id for row in alerts]))).all() if alerts else []
        session.expire_all()
        events = session.exec(select(RecommendationEvent).where(RecommendationEvent.subject_type == 'astronaut', RecommendationEvent.subject_id == person_id,
            RecommendationEvent.mission_id == mission_id, RecommendationEvent.status == 'pending')).all()
        metadata.update({'prediction_run_id': run.id, 'alerts': [{'id': row.id, 'indicator': row.indicator, 'severity': row.severity} for row in alerts],
            'notification_ids': [row.id for row in notifications], 'assessment_id': assessment.id, 'assessment_status': assessment.status,
            'ai_generation_status': assessment.report.get('generation_status'), 'ai_hypotheses': assessment.report.get('hypotheses', []),
            'recommendations': [{'id': row.id, 'generated': row.explanation.get('generated', False), 'state': row.explanation.get('state'),
                                 'generation_state': row.explanation.get('generation_state'), 'source_count': len(row.sources)} for row in events]})
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        if not metadata['alerts']:
            raise RuntimeError('No clinical alert was produced')
        if not any(row['generated'] for row in metadata['recommendations']) and not metadata['ai_hypotheses']:
            raise RuntimeError('No validated AI generation was produced; factual alerts remain available')


def main():
    parser = argparse.ArgumentParser(description='Create an individual development health case and execute the real AI assessment flow')
    parser.add_argument('--output', default='data/ai_health_case.json')
    args = parser.parse_args()
    path = Path(args.output)
    generate_case(create_case(path), path)


if __name__ == '__main__':
    main()
