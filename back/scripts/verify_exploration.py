"""Read-only API smoke checks for the exploration dataset."""
import json
from pathlib import Path
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.main import app
from app.database import engine
from app.models.preflight import Mission, MissionMember
from app.models.nutrition import MealLog


def main():
    credentials=json.loads(Path('/app/backups/exploration-access.json').read_text())
    with Session(engine) as s:
        mission=s.exec(select(Mission).where(Mission.status=='in_progress')).one()
        member=s.exec(select(MissionMember).where(MissionMember.mission_id==mission.id,MissionMember.role=='astronaut')).first()
        meal=s.exec(select(MealLog).where(MealLog.mission_id==mission.id,MealLog.mission_member_id==member.id)).first()
        mid,uid,mealid=mission.id,member.id,meal.id
    checks={
      'admin':['/v1/users/','/v1/missions','/v1/spacecraft','/v1/exams',f'/v1/missions/{mid}/operations'],
      'surgeon':[f'/v1/missions/{mid}/astronauts/{uid}/exams',f'/v1/missions/{mid}/astronauts/{uid}/nutrition-plans',f'/v1/missions/{mid}/astronauts/{uid}/nursing-records'],
      'commander':[f'/v1/missions/{mid}/meal-logs/{mealid}',f'/v1/missions/{mid}/mental-health/astronauts/{uid}'],
      'psychologist':[f'/v1/missions/{mid}/mental-health/astronauts/{uid}'],
      'nutritionist':[f'/v1/missions/{mid}/food-lots',f'/v1/missions/{mid}/astronauts/{uid}/nutrition-context'],
      'observer':['/v1/space-weather/events','/v1/space-weather/exposure-limits'],
    }
    count=0
    with TestClient(app) as client:
        for role,paths in checks.items():
            response=client.post('/v1/auth/login',json={'email':f'{role}@salus.example','password':credentials['password']})
            assert response.status_code==200,(role,response.text)
            headers={'Authorization':'Bearer '+response.json()['access_token']}
            for path in paths:
                result=client.get(path,headers=headers)
                assert result.status_code==200,(role,path,result.status_code,result.text[:400])
                count+=1
    print(f'Passed: {count} API read checks and {len(checks)} role logins.')

if __name__=='__main__':
    main()
