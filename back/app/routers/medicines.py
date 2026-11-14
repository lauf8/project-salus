from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.medicines import ActiveIngredient, Medicine
from app.models.user import User
from app.schemas.medicines import AllergyResponse, AllergyUpdate, MedicineCreate, MedicinePatch, MedicineResponse, NamedResponse, NameInput
from app.schemas.preflight import Page
from app.services.medicine_service import MedicineService


router = APIRouter(tags=['medicines'])


def get_medicine_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return MedicineService(session, user)


Service = Annotated[MedicineService, Depends(get_medicine_service)]


@router.get('/medicines', response_model=Page[MedicineResponse])
def list_medicines(service: Service, search: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_catalog(Medicine, search, page, per_page)


@router.post('/medicines', response_model=MedicineResponse, status_code=201)
def create_medicine(payload: MedicineCreate, service: Service):
    return service.save_medicine(payload)


@router.get('/medicines/{medicine_id}', response_model=MedicineResponse)
def get_medicine(medicine_id: int, service: Service):
    return service.get_medicine(medicine_id)


@router.patch('/medicines/{medicine_id}', response_model=MedicineResponse)
def update_medicine(medicine_id: int, payload: MedicinePatch, service: Service):
    return service.save_medicine(payload, medicine_id)


@router.delete('/medicines/{medicine_id}', status_code=204)
def delete_medicine(medicine_id: int, service: Service):
    service.delete_catalog(Medicine, medicine_id)
    return Response(status_code=204)


@router.get('/active-ingredients', response_model=Page[NamedResponse])
def list_ingredients(service: Service, search: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_catalog(ActiveIngredient, search, page, per_page)


@router.post('/active-ingredients', response_model=NamedResponse, status_code=201)
def create_ingredient(payload: NameInput, service: Service):
    return service.save_ingredient(payload)


@router.get('/active-ingredients/{ingredient_id}', response_model=NamedResponse)
def get_ingredient(ingredient_id: int, service: Service):
    return service._get(ActiveIngredient, ingredient_id)


@router.patch('/active-ingredients/{ingredient_id}', response_model=NamedResponse)
def update_ingredient(ingredient_id: int, payload: NameInput, service: Service):
    return service.save_ingredient(payload, ingredient_id)


@router.delete('/active-ingredients/{ingredient_id}', status_code=204)
def delete_ingredient(ingredient_id: int, service: Service):
    service.delete_catalog(ActiveIngredient, ingredient_id)
    return Response(status_code=204)


@router.get('/health/astronauts/{crew_member_id}/allergies', response_model=AllergyResponse)
def get_allergies(crew_member_id: int, service: Service, mission_id: int | None = Query(None, gt=0)):
    return service.get_allergies(crew_member_id, mission_id)


@router.put('/health/astronauts/{crew_member_id}/allergies', response_model=AllergyResponse)
def update_allergies(crew_member_id: int, payload: AllergyUpdate, service: Service, mission_id: int | None = Query(None, gt=0)):
    return service.update_allergies(crew_member_id, mission_id, payload)
