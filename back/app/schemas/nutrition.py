from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.preflight import InputModel, OutputModel


Unit = Literal['g', 'ml', 'serving', 'package', 'piece']
Basis = Literal['stored', 'prepared']
Quantity = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=6, allow_inf_nan=False)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=6, allow_inf_nan=False)]
MealType = Literal['breakfast', 'lunch', 'dinner', 'snack', 'hydration']
NUTRIENTS = ('energy_kcal', 'protein_g', 'carbohydrate_g', 'fat_g', 'fiber_g', 'sodium_mg')


class UnitEquivalence(InputModel):
    unit: Unit
    basis: Basis
    quantity_per_reference: Quantity


class FoodProductInput(InputModel):
    name: str = Field(min_length=1, max_length=200)
    category: Literal['food', 'beverage']
    is_plain_water: bool = False
    preservation_method: Literal['fresh', 'dehydrated', 'freeze_dried', 'thermostabilized', 'natural_form', 'other']
    physical_form: Literal['solid', 'paste', 'powder', 'liquid']
    reference_quantity: Quantity
    reference_unit: Unit
    reference_basis: Basis
    unit_equivalences: list[UnitEquivalence] = Field(default_factory=list, max_length=20)
    energy_kcal: Nonnegative | None = None
    protein_g: Nonnegative | None = None
    carbohydrate_g: Nonnegative | None = None
    fat_g: Nonnegative | None = None
    fiber_g: Nonnegative | None = None
    sodium_mg: Nonnegative | None = None
    preparation_method: Literal['ready_to_consume', 'rehydrate', 'heat', 'rehydrate_and_heat']
    preparation_water_ml: Nonnegative | None = None
    is_active: bool = True

    @model_validator(mode='after')
    def validate_equivalences(self):
        if self.is_plain_water and self.category != 'beverage':
            raise ValueError('Plain water must be a beverage')
        keys = [(self.reference_unit, self.reference_basis)]
        for equivalence in self.unit_equivalences:
            key = (equivalence.unit, equivalence.basis)
            if key in keys:
                raise ValueError('Each unit and basis must have exactly one equivalence')
            keys.append(key)
        return self


class FoodProductResponse(FoodProductInput, OutputModel):
    id: int


class FoodLotCreate(InputModel):
    food_product_id: int = Field(gt=0)
    lot_code: str = Field(min_length=1, max_length=200)
    expiration_date: date
    initial_quantity: Quantity
    stock_unit: Unit
    stock_basis: Basis = 'stored'


class FoodLotResponse(FoodLotCreate, OutputModel):
    id: int
    mission_id: int
    remaining_quantity: Decimal
    product_name: str
    status: Literal['available', 'expiring_soon', 'expired', 'depleted']
    is_expired: bool
    is_expiring_soon: bool
    is_depleted: bool
    expiration_warning_days: int


class MealItemInput(InputModel):
    id: int | None = Field(default=None, gt=0)
    food_product_id: int = Field(gt=0)
    lot_id: int = Field(gt=0)
    consumed_quantity: Quantity
    consumed_unit: Unit
    consumed_basis: Basis
    stock_quantity_used: Quantity | None = None
    preparation_water_used_ml: Nonnegative | None = None
    preparation_water_lot_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def validate_preparation_water(self):
        if self.preparation_water_lot_id is not None and not self.preparation_water_used_ml:
            raise ValueError('A preparation water lot requires a positive preparation water volume')
        return self


class MealInput(InputModel):
    mission_member_id: int = Field(gt=0)
    consumed_at: AwareDatetime
    meal_type: MealType
    notes: str | None = Field(default=None, max_length=5000)
    items: list[MealItemInput] = Field(min_length=1, max_length=100)


class MealCreate(MealInput):
    client_request_id: UUID | None = None


class MealUpdate(MealInput):
    expected_revision: int = Field(gt=0)


class MealItemResponse(OutputModel):
    id: int
    food_product_id: int
    lot_id: int
    consumed_quantity: Decimal
    consumed_unit: Unit
    consumed_basis: Basis
    stock_quantity_used: Decimal
    preparation_water_used_ml: Decimal | None
    preparation_water_lot_id: int | None
    product_snapshot: dict
    nutrients: dict[str, Decimal | None]
    beverage_volume_ml: Decimal | None
    plain_water_volume_ml: Decimal | None


class NutritionTotals(InputModel):
    nutrients: dict[str, Decimal]
    partial: dict[str, bool]
    beverage_volume_ml: Decimal
    beverage_volume_partial: bool
    plain_water_volume_ml: Decimal
    plain_water_volume_partial: bool
    preparation_water_used_ml: Decimal


class MealResponse(OutputModel):
    id: int
    mission_id: int
    mission_member_id: int
    consumed_at: datetime
    meal_type: MealType
    notes: str | None
    revision: int
    items: list[MealItemResponse]
    includes_plain_water: bool
    totals: NutritionTotals


class StockMovementResponse(OutputModel):
    id: int
    lot_id: int
    meal_log_item_id: int | None
    quantity: Decimal
    stock_unit: Unit
    movement_type: Literal['initial', 'consumption', 'reversal']
    purpose: str
    reverses_movement_id: int | None
    recorded_by_user_id: int
    recorded_at: datetime


class DailyNutritionResponse(InputModel):
    day: date
    timezone: str
    meals: list[MealResponse]
    totals: NutritionTotals
