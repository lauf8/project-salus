import json
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.database import get_session
from app.dependencies.donki import get_donki_client
from app.main import app
from app.models.preflight import Mission, MissionMember
from app.models.revoked_token import RevokedToken
from app.models.space_weather import (
    CrewActivity, ProtonFluxReading, RadiationDoseRecord, RadiationExposureLimit, RadiationFollowUp,
    SpaceWeatherEvent, SpaceWeatherEventLink, SpaceWeatherSyncRun,
)
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.models.user import User
from app.providers.donki import DonkiClient, DonkiSettings
from app.services.space_weather_service import date_windows, flare_peak_flux, linked_event_type, normalize_event, parse_donki_time


# Real October 2024 chain (DONKI format), reduced to the fields used.
FLARE = {
    'flrID': '2024-10-26T06:32:00-FLR-001', 'catalog': 'M2M_CATALOG',
    'instruments': [{'displayName': 'GOES-P: EXIS 1.0-8.0'}],
    'beginTime': '2024-10-26T06:32Z', 'peakTime': '2024-10-26T06:56Z', 'endTime': '2024-10-26T07:12Z',
    'classType': 'X1.8', 'sourceLocation': 'S16E62', 'activeRegionNum': 13869,
    'note': '', 'submissionTime': '2024-10-26T07:20Z', 'versionId': 1,
    'link': 'https://webtools.ccmc.gsfc.nasa.gov/DONKI/view/FLR/34210/-1',
    'linkedEvents': [{'activityID': '2024-10-26T06:48:00-CME-001'}, {'activityID': '2024-10-26T19:02:00-SEP-001'}],
}
CME = {
    'activityID': '2024-10-26T06:48:00-CME-001', 'catalog': 'M2M_CATALOG', 'startTime': '2024-10-26T06:48Z',
    'instruments': [{'displayName': 'SOHO: LASCO/C2'}], 'sourceLocation': 'S16E62', 'activeRegionNum': 13869,
    'note': 'Halo CME', 'submissionTime': '2024-10-26T09:00Z', 'versionId': 2, 'link': 'https://example.test/cme',
    'cmeAnalyses': [
        {'time21_5': '2024-10-26T08:40Z', 'latitude': -10.0, 'longitude': -50.0, 'halfAngle': 40.0, 'speed': 900.0, 'type': 'C', 'isMostAccurate': False},
        {'time21_5': '2024-10-26T08:30Z', 'latitude': -12.0, 'longitude': -55.0, 'halfAngle': 45.0, 'speed': 1100.0, 'type': 'O', 'isMostAccurate': True},
    ],
    'linkedEvents': [{'activityID': '2024-10-26T06:32:00-FLR-001'}, {'activityID': '2024-10-28T04:13:00-IPS-001'}],
}
SEP = {
    'sepID': '2024-10-26T19:02:00-SEP-001', 'eventTime': '2024-10-26T19:02Z',
    'instruments': [{'displayName': 'SOHO: COSTEP 28.2-50.1 MeV'}], 'submissionTime': '2024-10-26T19:35Z', 'versionId': 1,
    'link': 'https://example.test/sep',
    'linkedEvents': [{'activityID': '2024-10-26T06:32:00-FLR-001'}, {'activityID': '2024-10-26T06:48:00-CME-001'}, {'activityID': '2024-10-26T15:34:00-IPS-001'}],
}
OLD_FLARE = {**FLARE, 'flrID': '2023-01-10T00:00:00-FLR-001', 'beginTime': '2023-01-10T00:00Z', 'peakTime': None, 'endTime': None, 'classType': 'M2.0', 'linkedEvents': None}


class FakeDonki:
    """Simulates the DONKI API and records the calls."""

    def __init__(self):
        self.data = {'FLR': [FLARE, OLD_FLARE], 'CME': [CME], 'SEP': [SEP]}
        self.fail = {}
        self.calls = []

    def handler(self, request: httpx.Request):
        event_type = request.url.path.rsplit('/', 1)[-1]
        start, end = request.url.params['startDate'], request.url.params['endDate']
        self.calls.append((event_type, start, end, request.url.params['api_key']))
        if event_type in self.fail:
            return httpx.Response(self.fail[event_type])
        items = [item for item in self.data[event_type] if start <= (item.get('beginTime') or item.get('startTime') or item.get('eventTime'))[:10] <= end]
        return httpx.Response(200, content=json.dumps(items) if items else b'')


PROFILES = {'doctor': 'is_physician', 'astronaut': 'is_astronaut', 'outsider_doctor': 'is_physician'}


@pytest.fixture
def space_weather_api():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')

    models = (
        User, RevokedToken, Spacecraft, Mission, MissionMember, SpacecraftModule, SpaceWeatherEvent, SpaceWeatherEventLink,
        SpaceWeatherSyncRun, ProtonFluxReading, CrewActivity, RadiationExposureLimit, RadiationDoseRecord, RadiationFollowUp,
    )
    SQLModel.metadata.create_all(engine, tables=[model.__table__ for model in models])
    session = Session(engine)
    people = {}
    for name in ('doctor', 'astronaut', 'outsider_doctor'):
        user = User(name=name, email=f'sw-{name}@fictional.test', hashed_password='fictional', is_physician=name != 'astronaut', is_astronaut=name == 'astronaut')
        session.add(user)
        session.flush()
        people[name] = user.id
    mission = Mission(
        name='October mission', status='completed',
        planned_launch_at=datetime(2024, 10, 20, tzinfo=timezone.utc),
        started_at=datetime(2024, 10, 20, tzinfo=timezone.utc), ended_at=datetime(2024, 11, 5, tzinfo=timezone.utc),
    )
    session.add(mission)
    session.flush()
    session.add(MissionMember(mission_id=mission.id, user_id=people['doctor'], role='flight_surgeon'))
    session.add(MissionMember(mission_id=mission.id, user_id=people['astronaut'], role='astronaut'))
    session.add(RadiationExposureLimit(profile_id='nasa-sp-2009-3405-table-5-1', organ='bfo', period='30_day', value=250, unit='mGy-Eq', source_reference='Tabela 5-1'))
    session.commit()

    fake = FakeDonki()

    def get_test_session():
        yield session

    http_client = httpx.Client(transport=httpx.MockTransport(fake.handler))
    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_donki_client] = lambda: DonkiClient(http_client, DonkiSettings(api_key='TEST_KEY', base_url='https://donki.test/DONKI'))
    try:
        with TestClient(app) as client:
            def call(method, path, payload=None, expected=200, actor='doctor', params=None):
                # Public access: the identity is chosen through headers, without a token.
                headers = {'X-Public-User': str(people[actor]), 'X-Public-Profile': PROFILES[actor]}
                response = client.request(method, '/v1/space-weather' + path, json=payload, params=params, headers=headers)
                assert response.status_code == expected, response.text
                return response.json() if response.content else None
            yield call, session, fake, mission
    finally:
        app.dependency_overrides.clear()
        http_client.close()
        session.close()
        engine.dispose()


OCTOBER = {'start_date': '2024-10-01', 'end_date': '2024-11-14'}


# --- Normalization functions ---------------------------------------------------------------

def test_parse_donki_time_and_helpers():
    assert parse_donki_time('2024-10-26T19:02Z') == datetime(2024, 10, 26, 19, 2, tzinfo=timezone.utc)
    assert parse_donki_time('2024-10-26T19:02:30-03:00') == datetime(2024, 10, 26, 22, 2, 30, tzinfo=timezone.utc)
    assert parse_donki_time('') is None and parse_donki_time('not a date') is None and parse_donki_time(None) is None
    assert linked_event_type('2024-10-28T04:13:00-IPS-001') == 'IPS'
    assert linked_event_type('no-type') is None
    assert flare_peak_flux('X1.8') == pytest.approx(1.8e-4)
    assert flare_peak_flux('m2') == pytest.approx(2e-5)
    assert flare_peak_flux('C') == pytest.approx(1e-6)
    assert flare_peak_flux(None) is None and flare_peak_flux('Z9') is None
    assert list(date_windows(date(2024, 10, 1), date(2024, 11, 14))) == [(date(2024, 10, 1), date(2024, 10, 30)), (date(2024, 10, 31), date(2024, 11, 14))]


def test_normalize_uses_most_accurate_cme_analysis_and_skips_incomplete_items():
    fields, linked = normalize_event('CME', CME)
    assert fields['cme_speed_kms'] == 1100.0 and fields['cme_type'] == 'O' and fields['cme_half_angle_deg'] == 45.0
    assert linked == ['2024-10-26T06:32:00-FLR-001', '2024-10-28T04:13:00-IPS-001']
    assert normalize_event('SEP', {'eventTime': '2024-10-26T19:02Z'}) is None
    assert normalize_event('SEP', {'sepID': 'x', 'eventTime': None}) is None
    flare, _ = normalize_event('FLR', {**FLARE, 'endTime': '2024-10-26T06:00Z'})
    assert flare['end_time'] is None  # an end before the start is discarded


# --- API -----------------------------------------------------------------------------------

def test_sync_imports_events_links_and_uses_windows(space_weather_api):
    call, session, fake, _ = space_weather_api
    result = call('POST', '/sync', OCTOBER)
    runs = {run['event_type']: run for run in result['runs']}
    assert {key: (run['status'], run['fetched_count'], run['created_count']) for key, run in runs.items()} == {
        'FLR': ('success', 1, 1), 'CME': ('success', 1, 1), 'SEP': ('success', 1, 1),
    }
    # 45 days -> 2 windows of 30 days for each type, always with the configured key.
    assert len(fake.calls) == 6 and {call_[3] for call_ in fake.calls} == {'TEST_KEY'}

    flare = session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.event_type == 'FLR')).one()
    assert flare.flare_class == 'X1.8' and flare.flare_peak_flux_wm2 == pytest.approx(1.8e-4)
    assert flare.active_region_num == 13869 and flare.instruments == ['GOES-P: EXIS 1.0-8.0']
    assert len(session.exec(select(SpaceWeatherEventLink)).all()) == 7


def test_resync_is_idempotent_and_applies_new_versions(space_weather_api):
    call, session, fake, _ = space_weather_api
    call('POST', '/sync', OCTOBER)
    again = call('POST', '/sync', OCTOBER)
    assert [(run['created_count'], run['updated_count']) for run in again['runs']] == [(0, 0)] * 3

    fake.data['SEP'] = [{**SEP, 'versionId': 2, 'note': 'Revisado', 'linkedEvents': [{'activityID': '2024-10-26T06:32:00-FLR-001'}]}]
    revised = call('POST', '/sync', {**OCTOBER, 'event_types': ['SEP']})
    assert revised['runs'][0]['updated_count'] == 1
    sep = session.exec(select(SpaceWeatherEvent).where(SpaceWeatherEvent.event_type == 'SEP')).one()
    assert sep.version_id == 2 and sep.note == 'Revisado'
    links = session.exec(select(SpaceWeatherEventLink.linked_activity_id).where(SpaceWeatherEventLink.event_id == sep.id)).all()
    assert links == ['2024-10-26T06:32:00-FLR-001']
    assert session.exec(select(SpaceWeatherEvent)).all().__len__() == 3


def test_event_detail_shows_chain_in_both_directions(space_weather_api):
    call, *_ = space_weather_api
    call('POST', '/sync', OCTOBER)
    sep = call('GET', '/events/2024-10-26T19:02:00-SEP-001')
    assert sep['health_relevance'] == 'exposure'
    assert [(item['activity_id'], item['event_type'], item['stored']) for item in sep['linked_events']] == [
        ('2024-10-26T06:32:00-FLR-001', 'FLR', True),
        ('2024-10-26T06:48:00-CME-001', 'CME', True),
        ('2024-10-26T15:34:00-IPS-001', 'IPS', False),
    ]
    assert sep['linked_events'][0]['event']['flare_class'] == 'X1.8'

    flare = call('GET', '/events/2024-10-26T06:32:00-FLR-001')
    assert flare['health_relevance'] == 'precursor'
    assert {item['activity_id'] for item in flare['linked_events']} == {'2024-10-26T06:48:00-CME-001', '2024-10-26T19:02:00-SEP-001'}
    call('GET', '/events/inexistente', expected=404)


def test_lists_events_with_filters_and_mission_window(space_weather_api):
    call, _, _, mission = space_weather_api
    call('POST', '/sync', {'start_date': '2023-01-01', 'end_date': '2023-12-31', 'event_types': ['FLR']})
    call('POST', '/sync', OCTOBER)

    everything = call('GET', '/events')
    assert everything['pagination']['total'] == 4
    assert [item['event_type'] for item in call('GET', '/events', params={'event_type': 'SEP'})['data']] == ['SEP']
    recent = call('GET', '/events', params={'start': '2024-01-01T00:00:00Z'})
    assert recent['pagination']['total'] == 3
    call('GET', '/events', params={'start': '2024-01-01T00:00:00'}, expected=422)  # without time zone

    in_mission = call('GET', f'/missions/{mission.id}/events', actor='astronaut')
    assert {item['activity_id'] for item in in_mission['data']} == {FLARE['flrID'], CME['activityID'], SEP['sepID']}
    call('GET', f'/missions/{mission.id}/events', actor='outsider_doctor', expected=404)


def test_sync_permissions_and_validation(space_weather_api):
    call, *_ = space_weather_api
    call('POST', '/sync', OCTOBER, actor='astronaut', expected=403)
    call('POST', '/sync', OCTOBER, actor='outsider_doctor', expected=403)
    call('POST', '/sync', {'start_date': '2024-01-01', 'end_date': '2025-06-01'}, expected=422)
    call('POST', '/sync', {'start_date': '2024-02-01', 'end_date': '2024-01-01'}, expected=422)
    call('POST', '/sync', {**OCTOBER, 'event_types': ['GST']}, expected=422)
    call('POST', '/sync', {**OCTOBER, 'event_types': ['SEP', 'SEP']}, expected=422)
    # Public data: any authenticated user can query.
    call('GET', '/events', actor='astronaut')


def test_donki_failures_are_recorded(space_weather_api):
    call, session, fake, _ = space_weather_api
    fake.fail = {'CME': 500}
    partial = call('POST', '/sync', OCTOBER)
    assert [(run['event_type'], run['status']) for run in partial['runs']] == [('FLR', 'success'), ('CME', 'failed'), ('SEP', 'success')]

    fake.fail = {'FLR': 429, 'CME': 429, 'SEP': 429}
    failed = call('POST', '/sync', OCTOBER, expected=502)
    assert 'NASA_API_KEY' in failed['detail']['runs'][0]['error']
    statuses = session.exec(select(SpaceWeatherSyncRun.status)).all()
    assert statuses.count('failed') == 4 and statuses.count('success') == 2
    assert len(call('GET', '/sync-runs')) == 6


def test_exposure_limits(space_weather_api):
    call, *_ = space_weather_api
    limits = call('GET', '/exposure-limits', actor='astronaut')
    assert limits == [{'profile_id': 'nasa-sp-2009-3405-table-5-1', 'organ': 'bfo', 'period': '30_day', 'value': 250.0, 'unit': 'mGy-Eq', 'source_reference': 'Tabela 5-1'}]
    assert call('GET', '/exposure-limits', params={'profile_id': 'other'}) == []
