"""Creates a radiation flow demonstration scenario without internet access.

Usage (inside the container, after `alembic upgrade head`):
    python -m scripts.seed_radiation_demo

Creates:
- 4 users (choose them in the Profile and User selectors at the top of the screen):
    okafor@example.com  physician, mission administrator
    rivera@example.com  flight surgeon
    lima@example.com    astronaut (on EVA during the SEP)
    sato@example.com    astronaut (moved to the shelter)
- the in-progress mission "Radiation Demo", started 5 days ago;
- a recent fictional DONKI chain: flare X2.3 → CME → SEP 10 hours ago;
- Lima's EVA and Sato's shelter stay. The EVA opens Lima's 48 h window;
- simulated proton flux (8000 pfu peak), simulated doses and a nausea and fatigue report.

The events have fictional IDs; they are not real DONKI records. Run it on a development
database: the script refuses to run if the demonstration users already exist.
"""

import sys
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.core.security import hash_password
from app.database import engine
# Registers all models (foreign keys cross modules).
from app.models import health, health_alerts, knowledge, medicines, mental_health, notifications, nutrition, preflight, revoked_token, space_weather, spacecraft  # noqa: F401
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from app.schemas.radiation import CrewActivityCreate, DoseSimulationRequest, ProtonFluxSimulationRequest, SymptomReportCreate
from app.services.radiation_service import RadiationService
from app.services.space_weather_service import SpaceWeatherService


PASSWORD = 'secret123'
PEOPLE = [
    ('Cmdr. Okafor', 'okafor@example.com', True, False),  # also with the mission administrator profile
    ('Dr. Rivera', 'rivera@example.com', True, False),
    ('Ada Lima', 'lima@example.com', False, True),
    ('Kenji Sato', 'sato@example.com', False, True),
]


def donki_id(moment: datetime, kind: str) -> str:
    return f'{moment:%Y-%m-%dT%H:%M}:00-{kind}-001'


def donki_time(moment: datetime) -> str:
    return f'{moment:%Y-%m-%dT%H:%M}Z'


def main() -> int:
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    sep_time = now - timedelta(hours=10)
    flare_time, cme_time = sep_time - timedelta(hours=12), sep_time - timedelta(hours=11, minutes=40)
    flare_id, cme_id, sep_id = donki_id(flare_time, 'FLR'), donki_id(cme_time, 'CME'), donki_id(sep_time, 'SEP')

    with Session(engine) as session:
        if session.exec(select(User).where(User.email.in_([email for _, email, _, _ in PEOPLE]))).first():
            print('The demonstration users already exist; use a clean database.')
            return 1

        users = {}
        for name, email, physician, astronaut in PEOPLE:
            user = User(name=name, email=email, hashed_password=hash_password(PASSWORD), is_physician=physician, is_astronaut=astronaut, is_mission_admin=email.startswith('okafor'))
            session.add(user)
            session.flush()
            users[email.split('@')[0]] = user
        admin, doctor, lima, sato = users['okafor'], users['rivera'], users['lima'], users['sato']

        mission = Mission(name='Radiation Demo', status='in_progress', crew_size=2, planned_launch_at=now - timedelta(days=5), started_at=now - timedelta(days=5))
        session.add(mission)
        session.flush()
        for user, role in ((admin, 'mission_admin'), (doctor, 'flight_surgeon'), (lima, 'astronaut'), (sato, 'astronaut')):
            session.add(MissionMember(mission_id=mission.id, user_id=user.id, role=role))
        session.commit()

        # Chain in DONKI format, stored as if it came from the synchronization.
        items = {
            'FLR': [{
                'flrID': flare_id, 'beginTime': donki_time(flare_time), 'peakTime': donki_time(flare_time + timedelta(minutes=24)),
                'endTime': donki_time(flare_time + timedelta(minutes=50)), 'classType': 'X2.3', 'sourceLocation': 'S14W32',
                'activeRegionNum': 14210, 'instruments': [{'displayName': 'GOES-P: EXIS 1.0-8.0'}],
                'note': 'Fictional demonstration event', 'linkedEvents': [{'activityID': cme_id}, {'activityID': sep_id}],
            }],
            'CME': [{
                'activityID': cme_id, 'startTime': donki_time(cme_time), 'instruments': [{'displayName': 'SOHO: LASCO/C2'}],
                'note': 'Fictional demonstration event',
                'cmeAnalyses': [{'speed': 1850, 'halfAngle': 60, 'type': 'R', 'isMostAccurate': True}],
                'linkedEvents': [{'activityID': flare_id}],
            }],
            'SEP': [{
                'sepID': sep_id, 'eventTime': donki_time(sep_time), 'instruments': [{'displayName': 'GOES-P: SGPS >10 MeV'}],
                'note': 'Fictional demonstration event', 'linkedEvents': [{'activityID': flare_id}, {'activityID': cme_id}],
            }],
        }
        space_weather = SpaceWeatherService(session, None)
        for kind, rows in items.items():
            space_weather._store(kind, rows)
        session.commit()

        # The EVA recorded after the SEP opens Lima's 48 h window.
        RadiationService(session, lima).create_activity(mission.id, CrewActivityCreate(
            astronaut_id=lima.id, activity_type='eva', started_at=sep_time - timedelta(hours=2), ended_at=sep_time + timedelta(hours=3),
        ))
        RadiationService(session, admin).create_activity(mission.id, CrewActivityCreate(
            astronaut_id=sato.id, activity_type='storm_shelter', started_at=sep_time + timedelta(minutes=30), ended_at=sep_time + timedelta(hours=8),
        ))
        surgeon = RadiationService(session, doctor)
        surgeon.simulate_proton_flux(ProtonFluxSimulationRequest(event_activity_id=sep_id, peak_pfu=8000, rise_hours=3, decay_hours=10, duration_hours=10))
        surgeon.simulate_doses(mission.id, DoseSimulationRequest(start=sep_time, end=sep_time + timedelta(hours=9), event_activity_id=sep_id))
        follow_up = RadiationService(session, lima).list_follow_ups(mission.id, 'open', lima.id)[0]
        RadiationService(session, lima).add_report(mission.id, follow_up.id, SymptomReportCreate(
            symptoms=['nausea', 'fatigue'], reported_at=sep_time + timedelta(hours=5), note='Started about 2 h after the EVA',
        ))

        alerts = surgeon.list_alerts(mission.id, 'active', None, 1, 50)['data']
        print(f'Mission "{mission.name}" (id {mission.id}) created. SEP: {sep_id}')
        print('Active alerts: ' + ', '.join(f'{alert.rule_id} ({alert.severity})' for alert in alerts))
        print('At the top of the screen, choose Profile "Physician" + User "Dr. Rivera" (flight surgeon)')
        print('or Profile "Astronaut" + User "Ada Lima"; then Missions → Radiation Demo → Radiation tab.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
