from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.care import NursingRecordInput, NutritionPlanInput
from app.services.care_service import CareService


router = APIRouter(prefix="/missions/{mission_id}/astronauts/{member_id}", tags=["care"])


def service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return CareService(session, user)


Service = Annotated[CareService, Depends(service)]


@router.get("/nutrition-plans")
def nutrition_history(mission_id: int, member_id: int, manager: Service):
    return manager.history(mission_id, member_id, "nutrition")


@router.post("/nutrition-plans", status_code=201)
def create_nutrition_plan(mission_id: int, member_id: int, payload: NutritionPlanInput, manager: Service):
    return manager.save(mission_id, member_id, "nutrition", payload)


@router.put("/nutrition-plans/{record_id}")
def update_nutrition_plan(mission_id: int, member_id: int, record_id: int, payload: NutritionPlanInput, manager: Service):
    return manager.save(mission_id, member_id, "nutrition", payload, record_id)


@router.get("/nutrition-context")
def nutrition_context(mission_id: int, member_id: int, manager: Service):
    return manager.nutrition_context(mission_id, member_id)


@router.get("/nursing-records")
def nursing_history(mission_id: int, member_id: int, manager: Service):
    return manager.history(mission_id, member_id, "nursing")


@router.post("/nursing-records", status_code=201)
def create_nursing_record(mission_id: int, member_id: int, payload: NursingRecordInput, manager: Service):
    return manager.save(mission_id, member_id, "nursing", payload)


@router.put("/nursing-records/{record_id}")
def update_nursing_record(mission_id: int, member_id: int, record_id: int, payload: NursingRecordInput, manager: Service):
    return manager.save(mission_id, member_id, "nursing", payload, record_id)
