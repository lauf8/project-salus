"""Add English preflight simulation records for Alex without replacing other data."""
import math
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from sqlmodel import Session,select
from sqlalchemy import text
from scripts.seed_exploration import (engine,User,Mission,MissionMember,HealthObservation,MentalHealthCheckIn,
    NutritionPlan,NursingRecord,ExamDefinition,MissionExamRequirement,AstronautExam,ExamResult,ExamResultReview,
    FoodProduct,MissionFoodLot,FoodStockMovement,MealLog,MealLogItem,FoodProductResponse,NUTRIENTS,AccessAuditEvent)
from app.core.security import verify_password


def main():
    now=datetime.now(timezone.utc).replace(hour=6,minute=0,second=0,microsecond=0)
    with Session(engine) as s,s.begin():
        s.execute(text('SELECT pg_advisory_xact_lock(742306101)'))
        def add(cls,**kwargs):
            row=cls(**kwargs); s.add(row); s.flush(); return row
        alex=s.exec(select(User).where(User.email=='astronaut@salus.example')).one()
        assert not s.exec(select(MissionMember).where(MissionMember.user_id==alex.id)).first(),'Already assigned; no changes made'
        staff={key:s.exec(select(User).where(User.email==f'{key}@salus.example')).one() for key in ['operations','surgeon','nutritionist','nurse','psychologist','observer']}
        mission=add(Mission,name='Asteria 02 - Lunar Exploration Preflight Campaign',status='planned',crew_size=4,planned_launch_at=now+timedelta(days=45))
        member=add(MissionMember,mission_id=mission.id,user_id=alex.id,role='astronaut')
        roles={'operations':'mission_admin','surgeon':'flight_surgeon','nutritionist':'nutritionist','nurse':'nurse','psychologist':'psychologist','observer':'observer'}
        support={key:add(MissionMember,mission_id=mission.id,user_id=user.id,role=roles[key]) for key,user in staff.items()}
        alex.allergy_screening_completed=True
        for day in range(21):
            at=now-timedelta(days=20-day)
            busy=day%7 in (2,3)
            values={'heart_rate':round(65+3*math.sin(day)), 'respiratory_rate':14+day%3,'oxygen_saturation':98+day%2,
                'body_temperature':round(36.6+.1*math.sin(day),1),'sleep_duration':420 if busy else 465,
                'sleep_quality':3 if busy else 4,'fatigue':4 if busy else 2,'mood':4,'blood_glucose':88+day%7,
                'blood_pressure':None,'consciousness':None,'attention':None}
            for indicator,value in values.items():
                extra={'value':value}
                if indicator=='blood_pressure':extra={'systolic':116+day%5,'diastolic':74+day%3}
                if indicator in ('consciousness','attention'):extra={'category':'alert' if indicator=='consciousness' else 'usual'}
                add(HealthObservation,astronaut_id=alex.id,mission_id=mission.id,indicator=indicator,**extra,
                    collected_at=at,recorded_at=at+timedelta(minutes=10),recorded_by_user_id=staff['nurse'].id,
                    source='self_report' if indicator in ('sleep_duration','sleep_quality','fatigue','mood') else 'manual_measurement',
                    is_preflight_reference=day==0,activity='rest',signal_quality='good',symptoms_status='absent',
                    glucose_context='fasting' if indicator=='blood_glucose' else 'unknown',
                    note='Simulated ground-based preflight morning assessment; collected before training.')
            add(MentalHealthCheckIn,mission_id=mission.id,mission_member_id=member.id,check_in_date=at.date(),
                happiness_level=4,satisfaction_level=4,stress_level=3 if busy else 2,energy_level=3 if busy else 4,
                sleep_quality=3 if busy else 4,workload_level=4 if busy else 3,isolation_level=1,crew_connection_level=4,
                notes='Intensive simulator training today; recovery time protected.' if busy else 'Training progressing steadily; good support from the ground team.',
                created_at=at,updated_at=at,updated_by_user_id=alex.id)
        definitions=s.exec(select(ExamDefinition).order_by(ExamDefinition.id)).all()
        for i,definition in enumerate(definitions):
            req=add(MissionExamRequirement,mission_id=mission.id,exam_type_id=definition.exam_type_id,exam_definition_id=definition.id,due_days_before_launch=14)
            at=now-timedelta(days=7-i)
            exam=add(AstronautExam,mission_id=mission.id,mission_member_id=member.id,requirement_id=req.id,
                due_at=mission.planned_launch_at-timedelta(days=14),scheduled_at=at if i<5 else now+timedelta(days=3+i),
                definition_snapshot=definition.model_dump(mode='json'))
            if i>=5:continue
            field=definition.fields[0]['code']
            val={'hemoglobin':14.6,'heart_rate':65,'fev1':3.9,'visual_acuity':'20/20 both eyes','findings':'No active dental concerns identified in this simulated preflight assessment.'}[field]
            result=add(ExamResult,astronaut_exam_id=exam.id,performed_at=at,recorded_at=at+timedelta(hours=1),
                recorded_by_user_id=staff['surgeon'].id,summary='Simulated preflight assessment completed; recording available for review.',
                structured_values={field:val},exam_snapshot=exam.definition_snapshot,laboratory='Exploration Crew Medical Facility',performer_name=staff['surgeon'].name)
            if i<4:add(ExamResultReview,exam_result_id=result.id,reviewer_member_id=support['surgeon'].id,decision='accepted',notes='Reviewed for the preflight simulation checklist.',reviewed_at=at+timedelta(hours=2))
        add(NutritionPlan,mission_id=mission.id,mission_member_id=member.id,author_user_id=staff['nutritionist'].id,updated_by_user_id=staff['nutritionist'].id,
            valid_from=(now-timedelta(days=20)).date(),valid_until=mission.planned_launch_at.date(),energy_target_kcal=2600,hydration_target_ml=2500,
            dietary_guidance='Simulated preflight training plan: distribute intake across meals and review hydration around exercise. Energy and hydration values are scenario estimates, not a prescription.')
        for day in (15,8,1):
            add(NursingRecord,mission_id=mission.id,mission_member_id=member.id,author_user_id=staff['nurse'].id,updated_by_user_id=staff['nurse'].id,
                observed_at=now-timedelta(days=day),observations='Alert and comfortable after simulator session. No symptoms reported.',
                care_provided='Reviewed equipment contact points, recovery routine and symptom reporting.',sample_collection='Scheduled preflight sample collected and labeled.' if day==8 else 'No sample collection during this visit.')
        products=s.exec(select(FoodProduct).order_by(FoodProduct.id)).all()
        for product in products:
            water=product.is_plain_water
            daily=Decimal(2500 if water else 1)
            initial=Decimal(100000 if water else 60)
            lot=add(MissionFoodLot,mission_id=mission.id,food_product_id=product.id,lot_code=f'PREFLIGHT-ALEX-{product.id}',expiration_date=(now+timedelta(days=180)).date(),
                initial_quantity=initial,remaining_quantity=initial-daily*21,stock_unit=product.reference_unit)
            add(FoodStockMovement,lot_id=lot.id,quantity=initial,stock_unit=product.reference_unit,movement_type='initial',purpose='Ground training provision allocation',recorded_by_user_id=staff['operations'].id,recorded_at=now-timedelta(days=21))
            for day in range(21):
                # Use completed preceding days to avoid future-dated meals on the current day.
                at=now-timedelta(days=21-day)+timedelta(hours=products.index(product)*2)
                meal=add(MealLog,mission_id=mission.id,mission_member_id=member.id,consumed_at=at,
                    meal_type='hydration' if water else ['breakfast','lunch','dinner','snack'][products.index(product)],
                    notes='Simulated ground-based exploration menu familiarization.',recorded_by_user_id=alex.id,recorded_at=at)
                factor=daily/Decimal(product.reference_quantity)
                item=add(MealLogItem,meal_log_id=meal.id,food_product_id=product.id,lot_id=lot.id,consumed_quantity=daily,
                    consumed_unit=product.reference_unit,consumed_basis='stored',stock_quantity_used=daily,revision=1,
                    product_snapshot=FoodProductResponse.model_validate(product).model_dump(mode='json'),
                    nutrients={k:str(Decimal(getattr(product,k))*factor) for k in NUTRIENTS},beverage_volume_ml=daily if water else None,plain_water_volume_ml=daily if water else 0)
                add(FoodStockMovement,lot_id=lot.id,meal_log_item_id=item.id,quantity=-daily,stock_unit=product.reference_unit,movement_type='consumption',purpose='Ground training meal consumption',recorded_by_user_id=alex.id,recorded_at=at)
            assert s.execute(text('SELECT sum(quantity) FROM food_stock_movements WHERE lot_id=:id'),{'id':lot.id}).scalar_one()==lot.remaining_quantity
        add(AccessAuditEvent,actor_user_id=staff['operations'].id,resource_type='mission_member',resource_id=member.id,action='created',changed_fields=['mission_id','user_id','role'])
        print(f'Alex registered in mission {mission.id}: {mission.name}; 252 observations, 21 check-ins, 7 exams, 5 results, 105 meal logs, 1 nutrition plan, 3 nursing records.')

if __name__=='__main__': main()
