"""Replace application records with a coherent English exploration simulation.

Default: read-only inventory. --apply requires --database to match the connection.
Make a pg_dump backup first. No real people, flight events or clinical data are used.
"""
import argparse
import importlib
import json
import math
import os
import pkgutil
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import app.models
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, select

for module in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f'app.models.{module.name}')

from app.database import engine
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.preflight import Mission, MissionMember, ExamType, ExamDefinition, MissionExamRequirement, AstronautExam, ExamResult, ExamResultReview
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlertSettings, HealthAlert, HealthAlertEvent, HealthAlertObservation
from app.models.notifications import HealthNotification
from app.models.care import NutritionPlan, NursingRecord
from app.models.mental_health import MentalHealthCheckIn, PsychologyContactRequest, PsychologyFollowUp, MentalHealthAuditEvent
from app.models.nutrition import FoodProduct, MissionFoodLot, FoodStockMovement, MealLog, MealLogItem
from app.models.medicines import Medicine, ActiveIngredient, MedicineActiveIngredient, CrewMemberAllergy
from app.models.space_weather import SpaceWeatherEvent, SpaceWeatherEventLink, ProtonFluxReading, CrewActivity, RadiationDoseRecord, RadiationFollowUp
from app.models.access import AccessAuditEvent
from app.schemas.nutrition import FoodProductResponse, NUTRIENTS
from app.services.knowledge_transfer import import_public_knowledge
from scripts.knowledge import load_bundle, SEED_PATH

NOW = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)
RNG = random.Random(4217)


def inventory(session):
    quote = engine.dialect.identifier_preparer.quote
    return {t: session.execute(text(f'SELECT count(*) FROM {quote(t)}')).scalar_one() for t in sorted(inspect(engine).get_table_names())}


def populate(s, password):
    def add(record_type, **values):
        row = record_type(**values)
        s.add(row)
        s.flush()
        return row

    # DELETE preserves sequences: previous JWT subjects cannot become new users.
    tables = [t for t in SQLModel.metadata.sorted_tables if t.name != 'alembic_version']
    actual = set(inspect(engine).get_table_names()) - {'alembic_version'}
    assert actual == {t.name for t in tables}, 'Unmapped tables require review before reset'
    before = inventory(s)
    for table in reversed(tables):
        s.execute(table.delete())
    import_public_knowledge(s, load_bundle(SEED_PATH))
    hashed = hash_password(password)
    staff = {}
    for key, name, flag in [
        ('admin', 'Morgan Hayes', 'is_global_admin'), ('operations', 'Avery Bennett', 'is_mission_admin'),
        ('surgeon', 'Dr. Elena Ward', 'is_physician'), ('psychologist', 'Dr. Samuel Okafor', 'is_psychologist'),
        ('nutritionist', 'Dr. Priya Shah', 'is_nutritionist'), ('nurse', 'Jordan Ellis', 'is_nurse'),
        ('observer', 'Casey Brooks', 'is_observer'),
    ]:
        staff[key] = add(User, name=name, email=f'{key}@salus.example', hashed_password=hashed, **{flag: True})
    crew = [add(User, name=name, email=f'{key}@salus.example', is_astronaut=True,
                allergy_screening_completed=True, hashed_password=hashed) for key, name in [
                ('commander', 'Maya Chen'), ('pilot', 'Daniel Reyes'), ('engineer', 'Amara Nwosu'), ('scientist', 'Lucas Moreau')]]

    vehicles = []
    modules = []
    for i, (name, status) in enumerate([('Asteria Exploration Vehicle', 'in_use'), ('Horizon Transfer Vehicle', 'available')]):
        ship = add(Spacecraft, name=name, status=status, maximum_crew_capacity=4, model='Cislunar exploration concept',
                   manufacturer='Salus Exploration Program (simulation)', serial_number=f'SIM-CEV-{i+1:03}', manufactured_year=NOW.year,
                   description='Simulated four-person exploration vehicle. Concept specifications, not certified hardware.')
        vehicles.append(ship)
        current = []
        for code, title, purpose, volume in [('HAB', 'Crew Habitation', 'Sleep, meals, exercise and daily health monitoring', 62),
                ('LAB', 'Science and Medical Bay', 'Sample analysis and private medical consultations', 24),
                ('SHELTER', 'Radiation Storm Shelter', 'Protected occupancy during a simulated particle event', 12)]:
            current.append(add(SpacecraftModule, spacecraft_id=ship.id, code=code, name=title, purpose=purpose,
                               is_pressurized=True, is_habitable=True, pressurized_volume_m3=volume))
        modules.append(current)
    missions = [
        add(Mission, name='Asteria 01 - Lunar South Pole Reconnaissance', crew_size=4, spacecraft_id=vehicles[0].id,
            status='in_progress', planned_launch_at=NOW-timedelta(days=20), started_at=NOW-timedelta(days=20)),
        add(Mission, name='Horizon 02 - Cislunar Habitat Readiness', crew_size=4, spacecraft_id=vehicles[1].id,
            status='planned', planned_launch_at=NOW+timedelta(days=45)),
        add(Mission, name='Asteria Pathfinder - Orbital Systems Checkout', crew_size=4, spacecraft_id=vehicles[0].id,
            status='completed', planned_launch_at=NOW-timedelta(days=100), started_at=NOW-timedelta(days=100), ended_at=NOW-timedelta(days=86)),
    ]
    members = {}
    roles = {'operations':'mission_admin', 'surgeon':'flight_surgeon', 'psychologist':'psychologist', 'nutritionist':'nutritionist', 'nurse':'nurse', 'observer':'observer'}
    for mission in missions:
        for key, role in roles.items():
            members[mission.id, key] = add(MissionMember, mission_id=mission.id, user_id=staff[key].id, role=role)
        for i, user in enumerate(crew):
            members[mission.id, i] = add(MissionMember, mission_id=mission.id, user_id=user.id, role='astronaut')
        add(HealthAlertSettings, mission_id=mission.id, emergency_channel='Private flight surgeon operations channel',
            approved_by_user_id=staff['surgeon'].id, approval_note='Simulation profile only; not an operational medical protocol.')

    # Adapted recording fields, deliberately no invented NASA citations or thresholds.
    exams = [
        ('laboratory','Complete blood count','hemoglobin','Hemoglobin','g/dL',14.3),
        ('cardiology','Resting electrocardiogram','heart_rate','Heart rate','bpm',64),
        ('pulmonology','Pulmonary function assessment','fev1','FEV1','L',3.7),
        ('ophthalmology','Visual acuity assessment','visual_acuity','Corrected visual acuity','',None),
        ('dental','Dental readiness assessment','findings','Dental findings','',None),
        ('behavioral_health','Behavioral readiness interview','findings','Interview findings','',None),
        ('clinical_assessment','Aeromedical examination','findings','Examination findings','',None),
    ]
    for j,(code,name,field,label,unit,value) in enumerate(exams):
        typ = add(ExamType, code=code, name=code.replace('_',' ').title(), description='Mission-specific simulated assessment category')
        fields = [dict(code=field,label=label,type='number' if value is not None else 'text',unit=unit,required=True)]
        definition = add(ExamDefinition, exam_type_id=typ.id, code=f'exploration_{code}', name=name, description=name,
                         fields=fields, applicability_notes='Simulation recording template; clinical applicability requires physician review.')
        snapshot = definition.model_dump(mode='json')
        for mission in missions:
            req = add(MissionExamRequirement, mission_id=mission.id, exam_type_id=typ.id, exam_definition_id=definition.id, due_days_before_launch=14+j)
            for i,user in enumerate(crew):
                due = mission.planned_launch_at-timedelta(days=14+j)
                # Planned mission includes pending, scheduled, awaiting review and repeat requested.
                state = (i+j)%5 if mission.status=='planned' else 4
                exam = add(AstronautExam, mission_id=mission.id, mission_member_id=members[mission.id,i].id,
                           requirement_id=req.id, due_at=due, definition_snapshot=snapshot,
                           scheduled_at=due-timedelta(days=2) if state else None)
                if state < 2:
                    continue
                performed = due-timedelta(days=4) if mission.status!='planned' else NOW-timedelta(days=2)
                if mission.status=='planned':
                    exam.scheduled_at=performed
                result = add(ExamResult, astronaut_exam_id=exam.id, performed_at=performed, recorded_at=performed+timedelta(hours=1),
                             recorded_by_user_id=staff['surgeon'].id, summary='Assessment completed. Findings recorded for flight surgeon review.',
                             structured_values={field: round(value+i*.1,2) if value is not None else ('20/20 both eyes' if field=='visual_acuity' else 'No active concerns identified in this simulated assessment.')},
                             exam_snapshot=snapshot, laboratory='Exploration Crew Medical Facility', performer_name=staff['surgeon'].name)
                if state>=3:
                    add(ExamResultReview, exam_result_id=result.id, reviewer_member_id=members[mission.id,'surgeon'].id,
                        decision='repeat_requested' if state==3 else 'accepted', reviewed_at=performed+timedelta(hours=3),
                        notes='Repeat acquisition requested to confirm recording quality.' if state==3 else 'Reviewed and accepted for the simulated mission checklist.')

    # Common generic names, no prescribing or dosage guidance.
    ingredients = {}
    for name in ['Acetaminophen','Ibuprofen','Cetirizine','Ondansetron','Loperamide','Amoxicillin','Lidocaine','Hydrocortisone']:
        ingredient=add(ActiveIngredient,name=name)
        ingredients[name]=ingredient
        med=add(Medicine,name=name,main_indications='Medical kit reference; use requires flight surgeon assessment and formulation review.')
        add(MedicineActiveIngredient,medicine_id=med.id,active_ingredient_id=ingredient.id)
    add(CrewMemberAllergy,crew_member_id=crew[2].id,active_ingredient_id=ingredients['Amoxicillin'].id)

    active=missions[0]
    for mission in (missions[0],missions[2]):
        days=20 if mission.status=='in_progress' else 14
        for i,user in enumerate(crew):
            member=members[mission.id,i]
            for day in range(days):
                at=mission.started_at+timedelta(days=day,hours=1)
                busy=day%7 in (3,4)
                sleep=round(455+RNG.gauss(0,18)-(50 if busy else 0))
                vals={'heart_rate':round(62+i*3+RNG.gauss(0,3)), 'respiratory_rate':14+day%3,
                      'oxygen_saturation':98+day%2, 'body_temperature':round(36.6+RNG.gauss(0,.12),1),
                      'sleep_duration':sleep,'sleep_quality':3 if busy else 4,'fatigue':5 if busy else 2,
                      'mood':3 if busy else 4,'blood_glucose':round(87+i*2+RNG.gauss(0,4)),
                      'blood_pressure':None,'consciousness':None,'attention':None}
                for indicator,value in vals.items():
                    kwargs={'value':value}
                    if indicator=='blood_pressure': kwargs={'systolic':114+i*3+day%5,'diastolic':72+i+day%4}
                    if indicator in ('consciousness','attention'): kwargs={'category':'alert' if indicator=='consciousness' else 'usual'}
                    add(HealthObservation,astronaut_id=user.id,mission_id=mission.id,indicator=indicator,collected_at=at,recorded_at=at+timedelta(minutes=5),
                        recorded_by_user_id=staff['nurse'].id,source='self_report' if indicator in ('mood','fatigue','sleep_quality','sleep_duration') else 'manual_measurement',
                        activity='rest',signal_quality='good',glucose_context='fasting' if indicator=='blood_glucose' else 'unknown',
                        symptoms_status='absent',note='Morning crew health check after wake-up; simulated measurement.',**kwargs)
                add(MentalHealthCheckIn,mission_id=mission.id,mission_member_id=member.id,check_in_date=at.date(),
                    happiness_level=3 if busy else 4,satisfaction_level=4,stress_level=3 if busy else 2,energy_level=3 if busy else 4,
                    sleep_quality=3 if busy else 4,workload_level=4 if busy else 3,isolation_level=2,crew_connection_level=4,
                    notes='High workload after science operations; requested protected rest time.' if busy else 'Routine completed, team coordination steady, family message received.',
                    created_at=at,updated_at=at,updated_by_user_id=user.id)
            add(NutritionPlan,mission_id=mission.id,mission_member_id=member.id,author_user_id=staff['nutritionist'].id,
                updated_by_user_id=staff['nutritionist'].id,valid_from=mission.started_at.date(),valid_until=(mission.started_at+timedelta(days=35)).date(),
                energy_target_kcal=2600+i*150,hydration_target_ml=2500+i*100,
                dietary_guidance='Simulation planning targets. Rotate menu selections, distribute intake across meals, and review hydration around exercise and EVA. Individual needs require professional assessment.')
            add(NursingRecord,mission_id=mission.id,mission_member_id=member.id,author_user_id=staff['nurse'].id,updated_by_user_id=staff['nurse'].id,
                observed_at=mission.started_at+timedelta(days=days-1,hours=3),observations='Crew member alert and comfortable; no skin irritation reported after suit interface inspection.',
                care_provided='Completed equipment contact inspection and reviewed symptom reporting procedure.',sample_collection='Routine sample labeled and stored for scheduled analysis.')

    # A documented sleep disruption with an open operational follow-up, not a diagnosis.
    obs=add(HealthObservation,astronaut_id=crew[0].id,mission_id=active.id,indicator='sleep_duration',value=315,
            collected_at=NOW,recorded_at=NOW,source='self_report',recorded_by_user_id=crew[0].id,
            note='Sleep interrupted by scheduled habitat maintenance. Protected recovery period requested.')
    alert=add(HealthAlert,astronaut_id=crew[0].id,mission_id=active.id,rule_id='simulation_sleep_follow_up',rule_version='scenario-1',
              profile_snapshot={'simulation':True,'basis':'Documented crew report; scenario follow-up, not an automated clinical threshold'},
              indicator='sleep_duration',severity='attention',reason='Interrupted sleep after habitat maintenance; flight surgeon review pending.',trigger_observation_id=obs.id)
    add(HealthAlertObservation,alert_id=alert.id,observation_id=obs.id)
    add(HealthAlertEvent,alert_id=alert.id,observation_id=obs.id,actor_user_id=staff['surgeon'].id,action='created',severity='attention',status='open',reason=alert.reason,rule_version='scenario-1')
    add(HealthNotification,recipient_user_id=staff['surgeon'].id,mission_id=active.id,alert_id=alert.id,observation_id=obs.id,title='Crew sleep follow-up',message=alert.reason)
    request=add(PsychologyContactRequest,mission_id=active.id,mission_member_id=members[active.id,0].id,author_user_id=crew[0].id,
                updated_by_user_id=staff['psychologist'].id,status='fulfilled',created_at=NOW-timedelta(days=3))
    follow=add(PsychologyFollowUp,mission_id=active.id,mission_member_id=members[active.id,0].id,psychologist_user_id=staff['psychologist'].id,
               contact_request_id=request.id,session_at=NOW-timedelta(days=2),review_period_start=(NOW-timedelta(days=9)).date(),review_period_end=(NOW-timedelta(days=2)).date(),
               session_summary='Discussed workload concentration and communication delays. Crew member described effective peer support.',
               agreed_actions='Protect rest period and rebalance maintenance tasks with operations lead.',next_follow_up_on=(NOW+timedelta(days=5)).date(),
               share_agreed_actions=True,share_next_follow_up=True,updated_by_user_id=staff['psychologist'].id)
    add(MentalHealthAuditEvent,mission_id=active.id,actor_user_id=staff['psychologist'].id,resource_type='follow_up',resource_id=follow.id,action='created')

    # Ready-to-eat menus avoid unaccounted preparation water. Values are scenario estimates.
    products=[]
    menu=[('Oatmeal and fruit pouch',580,18,91,16,9,320),('Chicken rice and vegetables',820,45,106,24,10,740),
          ('Lentil stew and tortilla',780,32,109,24,18,690),('Nut and dried fruit mix',420,12,48,20,6,110),('Potable water',0,0,0,0,0,0)]
    for i,(name,kcal,protein,carbs,fat,fiber,sodium) in enumerate(menu):
        products.append(add(FoodProduct,name=name,category='beverage' if i==4 else 'food',is_plain_water=i==4,
            preservation_method='other' if i==4 else ('natural_form' if i==3 else 'thermostabilized'),physical_form='liquid' if i==4 else 'solid',
            reference_quantity=250 if i==4 else 1,reference_unit='ml' if i==4 else 'package',reference_basis='stored',
            energy_kcal=kcal,protein_g=protein,carbohydrate_g=carbs,fat_g=fat,fiber_g=fiber,sodium_mg=sodium,preparation_method='ready_to_consume',preparation_water_ml=0))
    for mission in missions:
        days=20 if mission==active else (14 if mission.status=='completed' else 0)
        lots=[]
        for i,p in enumerate(products):
            initial=Decimal(250000 if i==4 else 160)
            consumed=Decimal(days*4*(2500 if i==4 else 1))
            lot=add(MissionFoodLot,mission_id=mission.id,food_product_id=p.id,lot_code=f'{mission.id}-PROVISION-{i+1}',
                expiration_date=(NOW+timedelta(days=180)).date(),initial_quantity=initial,remaining_quantity=initial-consumed,stock_unit=p.reference_unit)
            lots.append(lot)
            add(FoodStockMovement,lot_id=lot.id,quantity=initial,stock_unit=p.reference_unit,movement_type='initial',purpose='Prelaunch provision allocation',recorded_by_user_id=staff['operations'].id,recorded_at=mission.planned_launch_at-timedelta(days=5))
        for day in range(days):
            for ci,user in enumerate(crew):
                for pi,p in enumerate(products):
                    at=mission.started_at+timedelta(days=day,hours=[1,6,12,9,13][pi])
                    quantity=Decimal(2500 if pi==4 else 1)
                    meal=add(MealLog,mission_id=mission.id,mission_member_id=members[mission.id,ci].id,consumed_at=at,
                        meal_type=['breakfast','lunch','dinner','snack','hydration'][pi],notes='Daily menu intake; simulated nutrition estimates.',recorded_by_user_id=user.id,recorded_at=at)
                    factor=quantity/Decimal(p.reference_quantity)
                    item=add(MealLogItem,meal_log_id=meal.id,food_product_id=p.id,lot_id=lots[pi].id,consumed_quantity=quantity,
                        consumed_unit=p.reference_unit,consumed_basis='stored',stock_quantity_used=quantity,
                        product_snapshot=FoodProductResponse.model_validate(p).model_dump(mode='json'),
                        nutrients={k:str(Decimal(getattr(p,k))*factor) for k in NUTRIENTS},beverage_volume_ml=quantity if pi==4 else None,
                        plain_water_volume_ml=quantity if pi==4 else 0,revision=1)
                    add(FoodStockMovement,lot_id=lots[pi].id,meal_log_item_id=item.id,quantity=-quantity,stock_unit=p.reference_unit,
                        movement_type='consumption',purpose='Recorded crew consumption',recorded_by_user_id=user.id,recorded_at=at)

    flare=add(SpaceWeatherEvent,activity_id='SIM-ASTERIA-FLR-001',event_type='FLR',catalog='Salus scenario simulation',
              start_time=NOW-timedelta(days=4,hours=3),end_time=NOW-timedelta(days=4,hours=2),flare_class='M2.1',note='Synthetic exercise event; not a NASA DONKI observation.',raw={'simulation':True})
    sep=add(SpaceWeatherEvent,activity_id='SIM-ASTERIA-SEP-001',event_type='SEP',catalog='Salus scenario simulation',
            start_time=NOW-timedelta(days=4),end_time=NOW-timedelta(days=3),note='Synthetic particle event used to rehearse shelter operations; not a measured solar event.',raw={'simulation':True})
    add(SpaceWeatherEventLink,event_id=sep.id,linked_activity_id=flare.activity_id,linked_event_type='FLR')
    for hour in range(96):
        add(ProtonFluxReading,observed_at=NOW-timedelta(hours=96-hour),energy_channel='>=30 MeV',flux_pfu=round(.2+12*math.exp(-((hour-18)/10)**2),3),satellite='SIMULATED-MONITOR',source='simulation')
    for i,user in enumerate(crew):
        for start,end,kind,module in [(active.started_at,NOW-timedelta(days=4),'iva',modules[0][0]),
                (NOW-timedelta(days=4),NOW-timedelta(days=4)+timedelta(hours=6),'storm_shelter',modules[0][2]),
                (NOW-timedelta(days=4)+timedelta(hours=6),NOW,'iva',modules[0][0])]:
            add(CrewActivity,mission_id=active.id,astronaut_id=user.id,activity_type=kind,started_at=start,ended_at=end,
                spacecraft_module_id=module.id,note='Simulated crew location log.',recorded_by_user_id=staff['operations'].id)
        for day in range(20):
            start=active.started_at+timedelta(days=day)
            add(RadiationDoseRecord,mission_id=active.id,astronaut_id=user.id,organ='bfo',dose=.35+(i*.01),period_start=start,
                period_end=start+timedelta(days=1),source='simulation',recorded_by_user_id=staff['surgeon'].id)
        add(RadiationFollowUp,event_id=sep.id,mission_id=active.id,astronaut_id=user.id,status='completed',was_on_eva=False,
            symptoms=[],notes='Completed simulated post-event observation; no symptoms reported. Not a clinical radiation assessment.',
            opened_at=sep.start_time,window_ends_at=sep.start_time+timedelta(hours=48),closed_at=sep.start_time+timedelta(hours=48),
            opened_by_user_id=staff['surgeon'].id,closed_by_user_id=staff['surgeon'].id)
    add(AccessAuditEvent,actor_user_id=staff['admin'].id,resource_type='simulation_dataset',resource_id=active.id,action='created',changed_fields=['missions','crew','operational_records'])

    # Validate balances against the ledger and items before committing any deletion.
    for lot in s.exec(select(MissionFoodLot)).all():
        balance=s.execute(text('SELECT sum(quantity) FROM food_stock_movements WHERE lot_id=:id'),{'id':lot.id}).scalar_one()
        assert balance==lot.remaining_quantity, f'Inventory mismatch {lot.id}'
    assert verify_password(password,staff['admin'].hashed_password)
    assert all(m.crew_size==len([u for u in s.exec(select(MissionMember).where(MissionMember.mission_id==m.id)).all() if u.role=='astronaut']) for m in missions)
    return {'database':engine.url.database,'scenario_date':NOW.isoformat(),'before':before,'after':inventory(s),
            'empty_table_reasons':{'alembic_version':'Migration metadata retained.', 'revoked_tokens':'New accounts have no logout history; user IDs are not reused.',
                'space_weather_sync_runs':'No external synchronization occurred; synthetic events must not claim a successful DONKI import.',
                'radiation_exposure_limits':'No operational radiation limits invented for this scenario.'}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--validate',action='store_true',help='Populate and check, then roll back all changes')
    parser.add_argument('--database')
    parser.add_argument('--report',default='/tmp/exploration-seed-report.json')
    args=parser.parse_args()
    with Session(engine) as session:
        if not (args.apply or args.validate):
            print(json.dumps(inventory(session),indent=2)); return
        if args.database!=engine.url.database:
            parser.error('--database must exactly match the configured database')
        password=os.environ.get('EXPLORATION_SEED_PASSWORD')
        if not password or len(password)<14:
            parser.error('EXPLORATION_SEED_PASSWORD must contain at least 14 characters')
        with session.begin():
            session.execute(text('SELECT pg_advisory_xact_lock(742306101)'))
            report=populate(session,password)
            if args.validate:
                session.rollback()
        Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
