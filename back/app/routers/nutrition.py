from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.nutrition import DailyNutritionResponse, FoodLotCreate, FoodLotResponse, FoodProductInput, FoodProductResponse, MealCreate, MealResponse, MealUpdate, StockMovementResponse
from app.schemas.preflight import Page
from app.services.nutrition_service import NutritionService


router = APIRouter(tags=['nutrition'])


def get_nutrition_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return NutritionService(session, user)


Service = Annotated[NutritionService, Depends(get_nutrition_service)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get('/food-products', response_model=Page[FoodProductResponse])
def list_products(service: Service, search: str | None = Query(None, max_length=200), category: Literal['food', 'beverage'] | None = None, page: PageNumber = 1, per_page: PageSize = 20):
    return service.list_products(search, category, page, per_page)


@router.post('/food-products', response_model=FoodProductResponse, status_code=201)
def create_product(payload: FoodProductInput, service: Service):
    return service.save_product(payload)


@router.get('/food-products/{product_id}', response_model=FoodProductResponse)
def get_product(product_id: int, service: Service):
    return service.get_product(product_id)


@router.put('/food-products/{product_id}', response_model=FoodProductResponse)
def update_product(product_id: int, payload: FoodProductInput, service: Service):
    return service.save_product(payload, product_id)


@router.get('/missions/{mission_id}/food-lots', response_model=Page[FoodLotResponse])
def list_lots(mission_id: int, service: Service, food_product_id: int | None = Query(None, gt=0), search: str | None = Query(None, max_length=200), status: Literal['expired', 'expiring_soon', 'depleted', 'usable'] | None = None, consumed_at: AwareDatetime | None = None, page: PageNumber = 1, per_page: PageSize = 20):
    return service.list_lots(mission_id, food_product_id, search, status, consumed_at, page, per_page)


@router.post('/missions/{mission_id}/food-lots', response_model=FoodLotResponse, status_code=201)
def create_lot(mission_id: int, payload: FoodLotCreate, service: Service):
    return service.create_lot(mission_id, payload)


@router.get('/missions/{mission_id}/food-lots/{lot_id}/movements', response_model=Page[StockMovementResponse])
def list_movements(mission_id: int, lot_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 20):
    return service.list_movements(mission_id, lot_id, page, per_page)


@router.post('/missions/{mission_id}/meal-logs', response_model=MealResponse, status_code=201)
def create_meal(mission_id: int, payload: MealCreate, service: Service):
    return service.create_meal(mission_id, payload)


@router.get('/missions/{mission_id}/meal-logs', response_model=Page[MealResponse])
def list_meals(mission_id: int, service: Service, mission_member_id: int | None = Query(None, gt=0), day: date | None = None, page: PageNumber = 1, per_page: PageSize = 20):
    return service.list_meals(mission_id, mission_member_id, day, page, per_page)


@router.get('/missions/{mission_id}/meal-logs/{meal_id}', response_model=MealResponse)
def get_meal(mission_id: int, meal_id: int, service: Service):
    return service.get_meal(mission_id, meal_id)


@router.put('/missions/{mission_id}/meal-logs/{meal_id}', response_model=MealResponse)
def update_meal(mission_id: int, meal_id: int, payload: MealUpdate, service: Service):
    return service.update_meal(mission_id, meal_id, payload)


@router.delete('/missions/{mission_id}/meal-logs/{meal_id}', status_code=204)
def delete_meal(mission_id: int, meal_id: int, service: Service, expected_revision: int = Query(ge=1)):
    service.delete_meal(mission_id, meal_id, expected_revision)
    return Response(status_code=204)


@router.get('/missions/{mission_id}/nutrition/daily', response_model=DailyNutritionResponse)
def daily_nutrition(mission_id: int, service: Service, mission_member_id: int = Query(gt=0), day: date = Query()):
    return service.daily(mission_id, mission_member_id, day)
