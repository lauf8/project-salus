from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from app.main import app
from app.database import get_session
from app.core.security import create_access_token
from app.models.user import User
from app.models.preflight import Mission, MissionMember
from app.models.space_weather import RadiationDoseRecord

@pytest.fixture
def radiation_api(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path / 'radiation.db'}",connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def foreign_keys(connection,_): connection.execute('PRAGMA foreign_keys=ON')
    SQLModel.metadata.create_all(engine,tables=[t for t in SQLModel.metadata.sorted_tables if t.name not in {'knowledge_documents','knowledge_passages'}])
    now=datetime.now(timezone.utc); ids={}
    with Session(engine) as s:
        for role in ('astronaut','other','surgeon','outsider','nurse','psychologist','nutritionist','admin'):
            row=User(name=role,email=f'{role}@test.example',hashed_password='unused',is_astronaut=role in ('astronaut','other'),is_physician=role in ('surgeon','outsider'),is_nurse=role=='nurse',is_psychologist=role=='psychologist',is_nutritionist=role=='nutritionist',is_global_admin=role=='admin')
            s.add(row);s.flush();ids[role]=row.id
        mission=Mission(name='Flight',planned_launch_at=now-timedelta(days=4),started_at=now-timedelta(days=4),status='in_progress')
        s.add(mission);s.flush();mid=mission.id
        for name,role in [('astronaut','astronaut'),('other','astronaut'),('surgeon','flight_surgeon'),('nurse','nurse'),('psychologist','psychologist'),('nutritionist','nutritionist')]:s.add(MissionMember(mission_id=mid,user_id=ids[name],role=role))
        for organ,unit,source,value in [('bfo','mGy-Eq','simulation',1),('bfo','mGy-Eq','simulation',2),('bfo','mGy','simulation',4),('skin','mGy-Eq','dosimeter',8)]:
            s.add(RadiationDoseRecord(mission_id=mid,astronaut_id=ids['astronaut'],organ=organ,unit=unit,source=source,dose=value,period_start=now-timedelta(days=2),period_end=now-timedelta(days=1),recorded_by_user_id=ids['surgeon']))
        s.commit()
    def dependency():
        with Session(engine) as s:yield s
    app.dependency_overrides[get_session]=dependency
    try:
        with TestClient(app) as client:
            def call(method='GET',path='',actor='astronaut',body=None):
                return client.request(method,f"/v1/missions/{mid}/astronauts/{ids['astronaut']}/radiation{path}",headers={'Authorization':f'Bearer {create_access_token(str(ids[actor]))}'},json=body)
            yield call,now
    finally:app.dependency_overrides.clear();engine.dispose()

def test_totals_preserve_organ_unit_and_source(radiation_api):
    call,_=radiation_api;result=call().json()
    assert len(result['totals'])==3
    assert next(t for t in result['totals'] if t['organ']=='bfo' and t['unit']=='mGy-Eq')['dose']==3
    assert result['can_record_dose'] is False

@pytest.mark.parametrize('actor',['other','outsider','psychologist','nutritionist','admin'])
def test_radiation_is_not_disclosed_to_unassigned_or_nonclinical_users(radiation_api,actor):
    call,_=radiation_api
    assert call(actor=actor).status_code==403

def test_only_assigned_physician_can_record_dose(radiation_api):
    call,now=radiation_api
    body=dict(organ='bfo',dose=.5,source='simulation',period_start=(now-timedelta(hours=2)).isoformat(),period_end=(now-timedelta(hours=1)).isoformat())
    for actor in ['astronaut','nurse','admin','outsider']:assert call('POST','/doses',actor,body).status_code==403
    assert call('POST','/doses','surgeon',body).status_code==201
    body['dose']=-1
    assert call('POST','/doses','surgeon',body).status_code==422

def test_activity_rejects_overlap_and_invalid_time(radiation_api):
    call,now=radiation_api
    body=dict(activity_type='iva',started_at=(now-timedelta(hours=4)).isoformat(),ended_at=(now-timedelta(hours=2)).isoformat())
    assert call('POST','/activities',body=body).status_code==201
    assert call('POST','/activities',body=body).status_code==409
    body['started_at']=(now+timedelta(hours=1)).isoformat()
    assert call('POST','/activities',body=body).status_code==422

def test_module_must_match_mission(radiation_api):
    call,now=radiation_api
    body=dict(activity_type='iva',started_at=(now-timedelta(hours=4)).isoformat(),spacecraft_module_id=99999)
    assert call('POST','/activities',body=body).status_code==422

def test_ongoing_activity_can_be_closed_once(radiation_api):
    call,now=radiation_api
    result=call('POST','/activities',body=dict(activity_type='iva',started_at=(now-timedelta(hours=1)).isoformat()))
    assert result.status_code==201
    path=f"/activities/{result.json()['id']}"
    body={'ended_at':now.isoformat()}
    assert call('PATCH',path,actor='other',body=body).status_code==403
    assert call('PATCH',path,body=body).status_code==200
    assert call('PATCH',path,body=body).status_code==409
