from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, JSON, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


def quantity_column():
    return Column(Numeric(20, 6), nullable=False)


class FoodProduct(SQLModel, table=True):
    __tablename__ = 'food_products'
    __table_args__ = (
        CheckConstraint("reference_basis IN ('stored', 'prepared')", name='ck_food_products_basis'),
        CheckConstraint("reference_unit IN ('g', 'ml', 'serving', 'package', 'piece')", name='ck_food_products_unit'),
        CheckConstraint("preservation_method IN ('fresh', 'dehydrated', 'freeze_dried', 'thermostabilized', 'natural_form', 'other')", name='ck_food_products_preservation'),
        CheckConstraint("physical_form IN ('solid', 'paste', 'powder', 'liquid')", name='ck_food_products_form'),
        CheckConstraint("preparation_method IN ('ready_to_consume', 'rehydrate', 'heat', 'rehydrate_and_heat')", name='ck_food_products_preparation'),
        CheckConstraint('energy_kcal >= 0 AND protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0 AND fiber_g >= 0 AND sodium_mg >= 0 AND preparation_water_ml >= 0', name='ck_food_products_nutrients'),
        CheckConstraint("category IN ('food', 'beverage')", name='ck_food_products_category'),
        CheckConstraint("NOT is_plain_water OR category = 'beverage'", name='ck_food_products_water'),
        CheckConstraint('reference_quantity > 0', name='ck_food_products_reference'),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    category: str
    is_plain_water: bool = False
    preservation_method: str
    physical_form: str
    reference_quantity: Decimal = Field(sa_column=quantity_column())
    reference_unit: str
    reference_basis: str
    unit_equivalences: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    energy_kcal: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    protein_g: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    carbohydrate_g: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    fat_g: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    fiber_g: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    sodium_mg: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    preparation_method: str
    preparation_water_ml: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    is_active: bool = True


class MissionFoodLot(SQLModel, table=True):
    __tablename__ = 'mission_food_lots'
    __table_args__ = (
        CheckConstraint("stock_basis IN ('stored', 'prepared')", name='ck_mission_food_lots_basis'),
        UniqueConstraint('mission_id', 'food_product_id', 'lot_code', name='uq_mission_food_lots_code'),
        UniqueConstraint('id', 'food_product_id', name='uq_mission_food_lots_product'),
        CheckConstraint('initial_quantity > 0 AND remaining_quantity >= 0 AND remaining_quantity <= initial_quantity', name='ck_mission_food_lots_balance'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    food_product_id: int = Field(foreign_key='food_products.id', index=True)
    lot_code: str
    expiration_date: date
    initial_quantity: Decimal = Field(sa_column=quantity_column())
    remaining_quantity: Decimal = Field(sa_column=quantity_column())
    stock_unit: str
    stock_basis: str = 'stored'


class MealLog(SQLModel, table=True):
    __tablename__ = 'meal_logs'
    __table_args__ = (
        ForeignKeyConstraint(['mission_member_id', 'mission_id'], ['mission_members.id', 'mission_members.mission_id'], name='fk_meal_logs_member_mission'),
        UniqueConstraint('mission_id', 'client_request_id', name='uq_meal_logs_request'),
        CheckConstraint("meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'hydration')", name='ck_meal_logs_type'),
        CheckConstraint('revision > 0', name='ck_meal_logs_revision'),
    )

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key='missions.id', index=True)
    mission_member_id: int = Field(index=True)
    consumed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    meal_type: str
    notes: str | None = None
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
    revision: int = 1
    is_deleted: bool = False
    client_request_id: str | None = None
    submission_hash: str | None = None


class MealLogItem(SQLModel, table=True):
    __tablename__ = 'meal_log_items'
    __table_args__ = (
        ForeignKeyConstraint(['lot_id', 'food_product_id'], ['mission_food_lots.id', 'mission_food_lots.food_product_id'], name='fk_meal_log_items_lot_product'),
        CheckConstraint('consumed_quantity > 0 AND stock_quantity_used > 0', name='ck_meal_log_items_quantities'),
        CheckConstraint('preparation_water_used_ml IS NULL OR preparation_water_used_ml >= 0', name='ck_meal_log_items_preparation_water'),
    )

    id: int | None = Field(default=None, primary_key=True)
    meal_log_id: int = Field(foreign_key='meal_logs.id', index=True)
    food_product_id: int = Field(foreign_key='food_products.id')
    lot_id: int = Field(index=True)
    consumed_quantity: Decimal = Field(sa_column=quantity_column())
    consumed_unit: str
    consumed_basis: str
    stock_quantity_used: Decimal = Field(sa_column=quantity_column())
    preparation_water_used_ml: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    preparation_water_lot_id: int | None = Field(default=None, foreign_key='mission_food_lots.id')
    product_snapshot: dict = Field(sa_column=Column(JSON, nullable=False))
    nutrients: dict = Field(sa_column=Column(JSON, nullable=False))
    beverage_volume_ml: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    plain_water_volume_ml: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    revision: int
    is_active: bool = True


class FoodStockMovement(SQLModel, table=True):
    __tablename__ = 'food_stock_movements'
    __table_args__ = (
        UniqueConstraint('reverses_movement_id', name='uq_food_stock_movements_reversal'),
        CheckConstraint("(movement_type = 'consumption' AND quantity < 0) OR (movement_type IN ('initial', 'reversal') AND quantity > 0)", name='ck_food_stock_movements_quantity'),
        CheckConstraint("movement_type IN ('initial', 'consumption', 'reversal')", name='ck_food_stock_movements_type'),
    )

    id: int | None = Field(default=None, primary_key=True)
    lot_id: int = Field(foreign_key='mission_food_lots.id', index=True)
    meal_log_item_id: int | None = Field(default=None, foreign_key='meal_log_items.id', index=True)
    quantity: Decimal = Field(sa_column=quantity_column())
    stock_unit: str
    movement_type: str
    purpose: str
    reverses_movement_id: int | None = Field(default=None, foreign_key='food_stock_movements.id')
    recorded_by_user_id: int = Field(foreign_key='users.id')
    recorded_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
