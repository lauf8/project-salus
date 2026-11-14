from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.roles import PROFILE_FIELDS
from app.database import get_session
from app.main import app
from app.models.access import AccessAuditEvent
from app.models.preflight import Mission, MissionMember
from app.models.user import User
from tests.public_identity import public_headers


@pytest.fixture
def access_api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'access.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    SQLModel.metadata.create_all(engine, tables=[t for t in SQLModel.metadata.sorted_tables if t.name not in {'knowledge_documents','knowledge_passages'}])
    with Session(engine) as session:
        users, members = {}, {}
        profiles = {'global':'is_global_admin','admin':'is_mission_admin','astronaut':'is_astronaut','other':'is_astronaut','doctor':'is_physician','psychologist':'is_psychologist','nutritionist':'is_nutritionist','nurse':'is_nurse','observer':'is_observer','outsider':'is_nutritionist','second_nurse':'is_nurse'}
        for name, profile in profiles.items():
            user = User(name=name,email=f'{name}@example.com',hashed_password='fictional',**{profile:True})
            session.add(user)
            session.flush()
            users[name]=user.id
        mission = Mission(name='Access mission',planned_launch_at=datetime.now(timezone.utc))
        other = Mission(name='Other mission',planned_launch_at=datetime.now(timezone.utc))
        session.add_all([mission,other]);session.flush()
        mission_id, other_id = mission.id, other.id
        roles={'admin':'mission_admin','astronaut':'astronaut','other':'astronaut','doctor':'flight_surgeon','psychologist':'psychologist','nutritionist':'nutritionist','nurse':'nurse','observer':'observer','second_nurse':'nurse'}
        for name, role in roles.items():
            member=MissionMember(mission_id=mission.id,user_id=users[name],role=role)
            session.add(member);session.flush();members[name]=member.id
        session.add(MissionMember(mission_id=other.id,user_id=users['outsider'],role='nutritionist'))
        session.commit()
    def get_test_session():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session]=get_test_session
    try:
        with TestClient(app) as client:
            def call(method,path,body=None,actor='admin',expected=200):
                response=client.request(method,'/v1'+path,json=body,headers=public_headers(engine,users[actor]))
                assert response.status_code==expected,response.text
                return response.json() if response.content else None
            yield call,engine,users,members,mission_id,other_id,client
    finally:
        app.dependency_overrides.clear();engine.dispose()


@pytest.mark.parametrize('profile',['is_nutritionist','is_nurse','is_observer','is_mission_admin'])
def test_new_profiles_register_without_astronaut_profile(client,profile):
    response=client.post('/v1/users/',json={'name':'New account','email':f'{profile}@example.com','password':'test123456','password_confirmation':'test123456','is_astronaut':False,profile:True})
    assert response.status_code==200,response.text
    assert response.json()[profile] is True
    assert response.json()['is_global_admin'] is False


def test_public_registration_rejects_privilege_escalation(client):
    for field in ('is_global_admin','is_active'):
        response=client.post('/v1/users/',json={'name':'No elevation','email':f'{field}@example.com','password':'test123456','password_confirmation':'test123456',field:True})
        assert response.status_code==422


def test_global_and_mission_administration_are_separate(access_api):
    call,engine,users,members,mid,other_id,_=access_api
    assert len(call('GET','/missions',actor='global')['data'])==2
    assert len(call('GET','/missions',actor='admin')['data'])==1
    call('PATCH',f'/missions/{other_id}',{'name':'Updated by global administrator'},actor='global')
    call('PATCH',f'/missions/{other_id}',{'name':'Forbidden'},expected=404)
    call('POST','/missions',{'name':'Managed by an operations administrator','planned_launch_at':datetime.now(timezone.utc).isoformat()},expected=201)
    call('POST','/missions',{'name':'Forbidden','planned_launch_at':datetime.now(timezone.utc).isoformat()},actor='observer',expected=403)
    for actor in ('global','admin','observer','nutritionist','nurse'):
        call('GET',f'/missions/{mid}/mental-health/astronauts/{members["astronaut"]}',actor=actor,expected=404 if actor=='global' else 403)
    for actor in ('global','admin','observer','nutritionist'):
        call('GET',f'/health/astronauts/{users["astronaut"]}/summary?mission_id={mid}',actor=actor,expected=403)
    operations=call('GET',f'/missions/{mid}/operations',actor='observer')
    assert operations['participants_by_role']['nurse']==2
    assert 'notes' not in str(operations)
    call('GET',f'/missions/{mid}/astronauts/{members["astronaut"]}/exams',actor='observer',expected=403)
    call('GET',f'/missions/{mid}/astronauts/{members["astronaut"]}/exams',actor='global',expected=404)
    call('PATCH',f'/missions/{mid}',{'name':'Forbidden observer edit'},actor='observer',expected=403)


def test_profile_admin_guards_and_inactive_accounts(access_api):
    call,engine,users,members,mid,_,_=access_api
    target=call('GET','/users/me',actor='global')
    body={name:target[name] for name in (*PROFILE_FIELDS,'is_active')}
    call('PUT',f'/users/{users["global"]}/profiles',{**body,'is_global_admin':False,'is_observer':True},actor='global',expected=409)
    call('PUT',f'/users/{users["global"]}/profiles',body,actor='admin',expected=403)
    observer=call('GET','/users/me',actor='observer')
    observer_body={name:observer[name] for name in (*PROFILE_FIELDS,'is_active')}
    call('PUT',f'/users/{users["observer"]}/profiles',{**observer_body,'is_global_admin':True},actor='global')
    call('PUT',f'/users/{users["global"]}/profiles',{**body,'is_global_admin':False,'is_observer':True},actor='global')
    call('PUT',f'/users/{users["global"]}/profiles',body,actor='global',expected=403)
    nurse=call('GET','/users/me',actor='nurse')
    nurse_body={name:nurse[name] for name in (*PROFILE_FIELDS,'is_active')}
    call('PUT',f'/users/{users["nurse"]}/profiles',{**nurse_body,'is_nurse':False,'is_observer':True},actor='observer',expected=409)
    call('PUT',f'/users/{users["nurse"]}/profiles',{**nurse_body,'is_active':False},actor='observer')
    call('GET','/users/me',actor='nurse',expected=404)  # conta inativa não pode ser selecionada
    audit=call('GET','/users/access-audit',actor='observer')
    assert audit['data'] and all('hashed_password' not in item for item in audit['data'])
    call('GET','/users/access-audit',actor='admin',expected=403)


def test_nursing_permissions_and_private_notes(access_api):
    call,engine,users,members,mid,_,_=access_api
    base=f'/missions/{mid}/astronauts/{members["astronaut"]}/nursing-records'
    payload={'observed_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),'observations':'Nursing-only clinical observation','care_provided':'Collected a sample','sample_collection':'Sample A'}
    record=call('POST',base,payload,actor='nurse',expected=201)
    call('PUT',base+f'/{record["id"]}',{**payload,'care_provided':'Updated care'},actor='nurse')
    for actor in ('astronaut','doctor','nurse','second_nurse'):
        assert len(call('GET',base,actor=actor))==1
    for actor in ('admin','observer','nutritionist','psychologist','other','global'):
        call('GET',base,actor=actor,expected=404 if actor=='global' else 403)
    call('PUT',base+f'/{record["id"]}',payload,actor='second_nurse',expected=403)
    call('PUT',f'/missions/{mid}/astronauts/{members["other"]}/nursing-records/{record["id"]}',payload,actor='nurse',expected=404)
    call('POST',base,{**payload,'prescription':'Forbidden'},actor='nurse',expected=422)
    call('POST',base,{**payload,'observed_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},actor='nurse',expected=422)
    observation={'mission_id':mid,'indicator':'heart_rate','value':80,'source':'manual_measurement','activity':'rest','collected_at':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()}
    call('POST',f'/health/astronauts/{users["astronaut"]}/observations',observation,actor='nurse',expected=201)
    summary=call('GET',f'/health/astronauts/{users["astronaut"]}/summary?mission_id={mid}',actor='nurse')
    assert summary['can_record'] is True and summary['can_set_reference'] is False
    assert summary['can_record_consciousness'] is False
    call('POST',f'/health/astronauts/{users["astronaut"]}/observations',{**observation,'is_preflight_reference':True},actor='nurse',expected=403)
    with Session(engine) as session:
        assert all('Nursing-only' not in str(event.model_dump()) for event in session.exec(select(AccessAuditEvent)).all())


def test_nutrition_permissions_and_restricted_context(access_api):
    call,engine,users,members,mid,_,_=access_api
    base=f'/missions/{mid}/astronauts/{members["astronaut"]}'
    payload={'valid_from':'2026-11-14','dietary_guidance':'Nutrition plan for this astronaut','energy_target_kcal':2200,'hydration_target_ml':2500}
    plan=call('POST',base+'/nutrition-plans',payload,actor='nutritionist',expected=201)
    call('PUT',base+f'/nutrition-plans/{plan["id"]}',{**payload,'energy_target_kcal':2300},actor='nutritionist')
    for actor in ('astronaut','doctor','nutritionist'):
        assert call('GET',base+'/nutrition-plans',actor=actor)[0]['energy_target_kcal']==2300
    for actor in ('nurse','admin','observer','other','global','outsider'):
        call('GET',base+'/nutrition-plans',actor=actor,expected=404 if actor in ('global','outsider') else 403)
    context=call('GET',base+'/nutrition-context',actor='nutritionist')
    assert set(context)=={'allergies','latest_blood_glucose'}
    call('POST',base+'/nutrition-plans',{**payload,'valid_until':'2026-11-13'},actor='nutritionist',expected=422)
    call('POST',base+'/nutrition-plans',{**payload,'energy_target_kcal':-1},actor='nutritionist',expected=422)
    call('GET',f'/missions/{mid}/nutrition/daily?mission_member_id={members["astronaut"]}&day=2026-11-14',actor='nutritionist')
    call('DELETE',f'/missions/{mid}/meal-logs/999?expected_revision=1',actor='nutritionist',expected=404)
    call('POST',f'/missions/{mid}/members',{'user_id':users['other'],'role':'nurse'},expected=422)
    call('DELETE',f'/missions/{mid}/members/{members["astronaut"]}',expected=409)



def test_bootstrap_requires_existing_account_and_only_initializes_once(access_api, monkeypatch):
    from scripts import bootstrap_global_admin

    call,engine,users,members,mid,_,_=access_api
    monkeypatch.setattr(bootstrap_global_admin,'engine',engine)
    monkeypatch.setattr('sys.argv',['bootstrap_global_admin','--email','admin@example.com'])
    with pytest.raises(SystemExit,match='already exists'):
        bootstrap_global_admin.main()
    with Session(engine) as session:
        administrator=session.get(User,users['global'])
        administrator.is_global_admin=False
        session.add(administrator)
        session.commit()
    monkeypatch.setattr('sys.argv',['bootstrap_global_admin','--email','missing@example.com'])
    with pytest.raises(SystemExit,match='existing account'):
        bootstrap_global_admin.main()
    monkeypatch.setattr('sys.argv',['bootstrap_global_admin','--email','admin@example.com'])
    bootstrap_global_admin.main()
    with Session(engine) as session:
        assert session.get(User,users['admin']).is_global_admin is True
        assert session.exec(select(AccessAuditEvent).where(AccessAuditEvent.action=='bootstrap_global_admin')).first()
