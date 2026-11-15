from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import os

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.nutrition import FoodProduct, FoodStockMovement, MealLog, MealLogItem, MissionFoodLot
from app.models.preflight import MissionMember
from app.schemas.nutrition import FoodLotResponse, FoodProductResponse, MealResponse, NUTRIENTS, NutritionTotals
from app.services.preflight_service import PreflightService, transactional


ZERO = Decimal('0')
PRECISION = Decimal('0.000001')


def rounded(value):
    if abs(value) > Decimal('99999999999999.999999'):
        raise HTTPException(422, 'The converted quantity exceeds the supported decimal precision')
    return value.quantize(PRECISION, rounding=ROUND_HALF_UP)


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def reference_amount(product, unit, basis):
    if product.reference_unit == unit and product.reference_basis == basis:
        return product.reference_quantity
    for entry in product.unit_equivalences:
        entry = entry.model_dump() if hasattr(entry, 'model_dump') else entry
        if entry['unit'] == unit and entry['basis'] == basis:
            return Decimal(str(entry['quantity_per_reference']))
    raise HTTPException(422, f'No registered equivalence for {product.name}: {basis} {unit}')


def total_items(items):
    nutrients = {key: ZERO for key in NUTRIENTS}
    partial = {key: False for key in NUTRIENTS}
    beverage = water = preparation = ZERO
    beverage_partial = water_partial = False
    for item in items:
        for key in NUTRIENTS:
            value = item.nutrients.get(key)
            if value is None:
                partial[key] = True
            else:
                nutrients[key] += Decimal(str(value))
        if item.product_snapshot['category'] == 'beverage':
            if item.beverage_volume_ml is None:
                beverage_partial = True
            else:
                beverage += item.beverage_volume_ml
        if item.product_snapshot['is_plain_water']:
            if item.plain_water_volume_ml is None:
                water_partial = True
            else:
                water += item.plain_water_volume_ml
        preparation += item.preparation_water_used_ml or ZERO
    return NutritionTotals(nutrients=nutrients, partial=partial, beverage_volume_ml=beverage,
                           beverage_volume_partial=beverage_partial, plain_water_volume_ml=water,
                           plain_water_volume_partial=water_partial, preparation_water_used_ml=preparation)


class NutritionService(PreflightService):
    def after_transactional_change(self, method_name, args, kwargs):
        if method_name not in {'create_lot', 'create_meal', 'update_meal', 'delete_meal'}:
            return
        from app.services.mission_risk_service import MissionRiskService
        service = MissionRiskService(self.session, self.user)
        mission_id = args[0] if args else kwargs['mission_id']
        if service.plan_at(mission_id, datetime.now(timezone.utc)) is not None:
            service.evaluate_internal(mission_id)

    def _movement(self, **values):
        lot = self.session.get(MissionFoodLot, values['lot_id'])
        product = self.get_product(lot.food_product_id)
        occurred_at = datetime.now(timezone.utc)
        if values.get('meal_log_item_id'):
            item = self.session.get(MealLogItem, values['meal_log_item_id'])
            occurred_at = self.session.get(MealLog, item.meal_log_id).consumed_at
        reference_delta = Decimal(str(values['quantity'])) / reference_amount(product, lot.stock_unit, lot.stock_basis)
        if values.get('reverses_movement_id'):
            original = self.session.get(FoodStockMovement, values['reverses_movement_id'])
            if original.risk_snapshot:
                occurred_at = datetime.fromisoformat(original.risk_snapshot['event_at'])
                reference_delta = -Decimal(original.risk_snapshot['reference_delta'])
        snapshot = {'reference_delta': str(reference_delta), 'event_at': as_utc(occurred_at).isoformat(),
                    'food_name': product.name, 'expiration_date': lot.expiration_date.isoformat(),
                    'unit': product.reference_unit, 'quantity_per_reference': str(product.reference_quantity)}
        return FoodStockMovement(**values, risk_snapshot=snapshot)

    def get_product(self, product_id, lock=False):
        statement = select(FoodProduct).where(FoodProduct.id == product_id)
        if lock:
            statement = statement.with_for_update()
        product = self.session.exec(statement).first()
        if product is None:
            raise HTTPException(404, 'Food product not found')
        return product

    def list_products(self, search, category, page, per_page):
        statement = select(FoodProduct)
        if search:
            statement = statement.where(FoodProduct.name.icontains(search.strip(), autoescape=True))
        if category:
            statement = statement.where(FoodProduct.category == category)
        return self._page(statement.order_by(FoodProduct.name, FoodProduct.id), page, per_page)

    def _food_catalog_writer(self):
        if self.user.is_nutritionist and self.session.exec(select(MissionMember).where(MissionMember.user_id == self.user.id, MissionMember.role == 'nutritionist')).first():
            return
        self._catalog_writer()

    @transactional
    def save_product(self, payload, product_id=None):
        self._food_catalog_writer()
        values = payload.model_dump()
        values['unit_equivalences'] = payload.model_dump(mode='json')['unit_equivalences']
        product = self.get_product(product_id, lock=True) if product_id else FoodProduct(**values)
        for key, value in values.items():
            setattr(product, key, value)
        self.session.add(product)
        self.session.flush()
        return FoodProductResponse.model_validate(product)

    def _stock_writer(self, mission_id, lock=False):
        mission, actor = self._access(mission_id, {'mission_admin', 'flight_surgeon'}, lock=lock)
        if actor.role == 'flight_surgeon':
            self._require_physician()
        return mission

    def _meal_access(self, mission_id, member_id, lock=False, write=False):
        mission, actor = self._access(mission_id, {'astronaut', 'flight_surgeon', 'nutritionist'}, lock=lock)
        if actor.role == 'nutritionist':
            if not self.user.is_nutritionist or write:
                raise HTTPException(403, 'Nutritionists may consult meal records but cannot change the astronaut journal')
        target = self.session.get(MissionMember, member_id)
        if target is None or target.mission_id != mission_id or target.role != 'astronaut':
            raise HTTPException(404, 'Astronaut membership not found in this mission')
        if actor.role == 'flight_surgeon':
            self._require_physician()
        elif actor.role == 'astronaut' and target.user_id != self.user.id:
            raise HTTPException(403, 'Astronauts may only access their own meal records')
        return mission

    def _lot(self, mission_id, lot_id):
        lot = self.session.get(MissionFoodLot, lot_id)
        if lot is None or lot.mission_id != mission_id:
            raise HTTPException(404, 'Food lot not found in this mission')
        return lot

    def _lot_response(self, lot, consumed_at=None):
        day = as_utc(consumed_at or datetime.now(timezone.utc)).date()
        warning = max(0, int(os.getenv('FOOD_EXPIRATION_WARNING_DAYS', '7')))
        expired = lot.expiration_date < day
        expiring = not expired and lot.expiration_date <= day + timedelta(days=warning)
        depleted = lot.remaining_quantity == ZERO
        return FoodLotResponse(**lot.model_dump(), product_name=self.get_product(lot.food_product_id).name,
                               status='depleted' if depleted else 'expired' if expired else 'expiring_soon' if expiring else 'available',
                               is_expired=expired, is_expiring_soon=expiring, is_depleted=depleted, expiration_warning_days=warning)

    def list_lots(self, mission_id, product_id, search, status, consumed_at, page, per_page):
        self._access(mission_id)
        statement = select(MissionFoodLot).join(FoodProduct).where(MissionFoodLot.mission_id == mission_id)
        day = as_utc(consumed_at or datetime.now(timezone.utc)).date()
        warning = max(0, int(os.getenv('FOOD_EXPIRATION_WARNING_DAYS', '7')))
        if product_id:
            statement = statement.where(MissionFoodLot.food_product_id == product_id)
        if search:
            statement = statement.where(FoodProduct.name.icontains(search.strip(), autoescape=True) | MissionFoodLot.lot_code.icontains(search.strip(), autoescape=True))
        if status == 'expired':
            statement = statement.where(MissionFoodLot.expiration_date < day)
        elif status == 'depleted':
            statement = statement.where(MissionFoodLot.remaining_quantity == 0)
        elif status == 'usable':
            statement = statement.where(MissionFoodLot.expiration_date >= day, MissionFoodLot.remaining_quantity > 0)
        elif status == 'expiring_soon':
            statement = statement.where(MissionFoodLot.expiration_date >= day, MissionFoodLot.expiration_date <= day + timedelta(days=warning), MissionFoodLot.remaining_quantity > 0)
        result = self._page(statement.order_by(MissionFoodLot.expiration_date, MissionFoodLot.id), page, per_page)
        result['data'] = [self._lot_response(lot, consumed_at) for lot in result['data']]
        return result

    @transactional
    def create_lot(self, mission_id, payload):
        self._stock_writer(mission_id, lock=True)
        product = self.get_product(payload.food_product_id)
        if not product.is_active:
            raise HTTPException(409, 'Inactive products cannot receive new lots')
        reference_amount(product, payload.stock_unit, payload.stock_basis)
        lot = MissionFoodLot(mission_id=mission_id, remaining_quantity=payload.initial_quantity, **payload.model_dump())
        self.session.add(lot)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, 'A lot with this code already exists for this product in this mission') from exc
        self.session.add(self._movement(lot_id=lot.id, quantity=lot.initial_quantity, stock_unit=lot.stock_unit,
                                          movement_type='initial', purpose='receipt', recorded_by_user_id=self.user.id))
        self.session.flush()
        return self._lot_response(lot)

    def list_movements(self, mission_id, lot_id, page, per_page):
        self._stock_writer(mission_id)
        self._lot(mission_id, lot_id)
        return self._page(select(FoodStockMovement).where(FoodStockMovement.lot_id == lot_id).order_by(FoodStockMovement.id), page, per_page)

    def _prepare_items(self, mission_id, payload, old_items=None):
        old_by_id = {item.id: item for item in old_items or []}
        used_ids = set()
        prepared = []
        for entry in payload.items:
            lot = self._lot(mission_id, entry.lot_id)
            if lot.food_product_id != entry.food_product_id:
                raise HTTPException(422, 'The food product does not match the selected lot')
            if lot.expiration_date < as_utc(payload.consumed_at).date():
                raise HTTPException(409, f'Lot {lot.lot_code} is expired at the meal time (UTC)')
            product = self.get_product(entry.food_product_id)
            if entry.id is not None:
                previous = old_by_id.get(entry.id)
                if previous is None or previous.food_product_id != entry.food_product_id or entry.id in used_ids:
                    raise HTTPException(422, 'Invalid existing meal item')
                used_ids.add(entry.id)
                product = FoodProductResponse.model_validate(previous.product_snapshot)
            elif not product.is_active:
                raise HTTPException(409, 'Inactive products cannot be added to a meal')
            factor = entry.consumed_quantity / reference_amount(product, entry.consumed_unit, entry.consumed_basis)
            required_stock = rounded(factor * reference_amount(product, lot.stock_unit, lot.stock_basis))
            stock_used = entry.stock_quantity_used if entry.stock_quantity_used is not None else required_stock
            if stock_used <= ZERO or stock_used < required_stock:
                raise HTTPException(422, 'Stock quantity used must cover the consumed quantity in the lot unit')
            snapshot = FoodProductResponse.model_validate(product).model_dump(mode='json')
            nutrients = {key: str(rounded(getattr(product, key) * factor)) if getattr(product, key) is not None else None for key in NUTRIENTS}
            beverage = None
            if product.category == 'beverage':
                try:
                    beverage = rounded(factor * reference_amount(product, 'ml', entry.consumed_basis))
                except HTTPException:
                    pass
            water_lot = None
            water_stock = ZERO
            if entry.preparation_water_lot_id:
                water_lot = self._lot(mission_id, entry.preparation_water_lot_id)
                water_product = self.get_product(water_lot.food_product_id)
                if not water_product.is_plain_water or water_product.category != 'beverage':
                    raise HTTPException(422, 'Preparation water must come from a plain water lot')
                if water_lot.expiration_date < as_utc(payload.consumed_at).date():
                    raise HTTPException(409, 'The preparation water lot is expired at the meal time (UTC)')
                water_stock = rounded(entry.preparation_water_used_ml / reference_amount(water_product, 'ml', 'stored') * reference_amount(water_product, water_lot.stock_unit, water_lot.stock_basis))
                if water_stock <= ZERO:
                    raise HTTPException(422, 'Preparation water quantity is below stock precision')
            prepared.append((MealLogItem(food_product_id=entry.food_product_id, lot_id=lot.id,
                                         consumed_quantity=entry.consumed_quantity, consumed_unit=entry.consumed_unit,
                                         consumed_basis=entry.consumed_basis, stock_quantity_used=stock_used,
                                         preparation_water_used_ml=entry.preparation_water_used_ml,
                                         preparation_water_lot_id=entry.preparation_water_lot_id,
                                         product_snapshot=snapshot, nutrients=nutrients, beverage_volume_ml=beverage,
                                         plain_water_volume_ml=beverage if product.is_plain_water else ZERO,
                                         revision=1, meal_log_id=0), water_lot, water_stock))
        return prepared

    def _active_items(self, meal_id):
        return self.session.exec(select(MealLogItem).where(MealLogItem.meal_log_id == meal_id, MealLogItem.is_active == True).order_by(MealLogItem.id)).all()

    def _meal_response(self, meal):
        items = self._active_items(meal.id)
        return MealResponse(**meal.model_dump(), items=items,
                            includes_plain_water=any(item.product_snapshot['is_plain_water'] for item in items), totals=total_items(items))

    def _apply_items(self, mission_id, meal, prepared, old_items):
        old_ids = [item.id for item in old_items]
        old_movements = self.session.exec(select(FoodStockMovement).where(FoodStockMovement.meal_log_item_id.in_(old_ids), FoodStockMovement.movement_type == 'consumption')).all() if old_ids else []
        changes = defaultdict(lambda: ZERO)
        for movement in old_movements:
            changes[movement.lot_id] -= movement.quantity
        for item, water_lot, water_stock in prepared:
            changes[item.lot_id] -= item.stock_quantity_used
            if water_lot:
                changes[water_lot.id] -= water_stock
        for lot_id in sorted(changes):
            lot = self.session.exec(select(MissionFoodLot).where(MissionFoodLot.id == lot_id, MissionFoodLot.mission_id == mission_id).with_for_update().execution_options(populate_existing=True)).first()
            if lot is None:
                raise HTTPException(404, 'Food lot not found in this mission')
            delta = changes[lot_id]
            result = self.session.execute(update(MissionFoodLot).where(MissionFoodLot.id == lot_id,
                MissionFoodLot.remaining_quantity + delta >= 0,
                MissionFoodLot.remaining_quantity + delta <= MissionFoodLot.initial_quantity).values(remaining_quantity=MissionFoodLot.remaining_quantity + delta))
            if result.rowcount != 1:
                raise HTTPException(409, f'Insufficient stock or concurrent stock conflict for lot {lot.lot_code}. Refresh the available lots.')
        for movement in old_movements:
            self.session.add(self._movement(lot_id=movement.lot_id, meal_log_item_id=movement.meal_log_item_id,
                                              quantity=-movement.quantity, stock_unit=movement.stock_unit, movement_type='reversal',
                                              purpose=movement.purpose, reverses_movement_id=movement.id, recorded_by_user_id=self.user.id))
        for item in old_items:
            item.is_active = False
            self.session.add(item)
        for item, water_lot, water_stock in prepared:
            item.meal_log_id = meal.id
            item.revision = meal.revision
            self.session.add(item)
            self.session.flush()
            lot = self._lot(mission_id, item.lot_id)
            self.session.add(self._movement(lot_id=lot.id, meal_log_item_id=item.id, quantity=-item.stock_quantity_used,
                                              stock_unit=lot.stock_unit, movement_type='consumption', purpose='meal', recorded_by_user_id=self.user.id))
            if water_lot:
                self.session.add(self._movement(lot_id=water_lot.id, meal_log_item_id=item.id, quantity=-water_stock,
                                                  stock_unit=water_lot.stock_unit, movement_type='consumption', purpose='preparation_water', recorded_by_user_id=self.user.id))
        self.session.flush()

    @transactional
    def create_meal(self, mission_id, payload):
        self._meal_access(mission_id, payload.mission_member_id, lock=True, write=True)
        request_id = str(payload.client_request_id) if payload.client_request_id else None
        fingerprint = sha256(json.dumps(payload.model_dump(mode='json', exclude={'client_request_id'}), sort_keys=True).encode()).hexdigest()
        if request_id:
            previous = self.session.exec(select(MealLog).where(MealLog.mission_id == mission_id, MealLog.client_request_id == request_id)).first()
            if previous:
                if previous.submission_hash != fingerprint or previous.is_deleted:
                    raise HTTPException(409, 'This request ID has already been used for a different or deleted meal')
                return self._meal_response(previous)
        prepared = self._prepare_items(mission_id, payload)
        meal = MealLog(mission_id=mission_id, mission_member_id=payload.mission_member_id, consumed_at=payload.consumed_at,
                       meal_type=payload.meal_type, notes=payload.notes, recorded_by_user_id=self.user.id,
                       client_request_id=request_id, submission_hash=fingerprint)
        self.session.add(meal)
        self.session.flush()
        self._apply_items(mission_id, meal, prepared, [])
        return self._meal_response(meal)

    def _meal(self, mission_id, meal_id, write=False):
        meal = self.session.exec(select(MealLog).where(MealLog.id == meal_id, MealLog.mission_id == mission_id).with_for_update()).first()
        if meal is None:
            raise HTTPException(404, 'Meal not found in this mission')
        self._meal_access(mission_id, meal.mission_member_id, write=write)
        return meal

    def get_meal(self, mission_id, meal_id):
        self._access(mission_id)
        meal = self._meal(mission_id, meal_id)
        if meal.is_deleted:
            raise HTTPException(404, 'Meal not found')
        return self._meal_response(meal)

    @transactional
    def update_meal(self, mission_id, meal_id, payload):
        self._meal_access(mission_id, payload.mission_member_id, lock=True, write=True)
        meal = self._meal(mission_id, meal_id, write=True)
        if meal.is_deleted or payload.expected_revision != meal.revision:
            raise HTTPException(409, 'The meal has changed. Reload it before editing.')
        old_items = self._active_items(meal.id)
        prepared = self._prepare_items(mission_id, payload, old_items)
        meal.revision += 1
        meal.mission_member_id = payload.mission_member_id
        meal.consumed_at = payload.consumed_at
        meal.meal_type = payload.meal_type
        meal.notes = payload.notes
        self.session.add(meal)
        self._apply_items(mission_id, meal, prepared, old_items)
        return self._meal_response(meal)

    @transactional
    def delete_meal(self, mission_id, meal_id, expected_revision):
        self._access(mission_id, lock=True)
        meal = self._meal(mission_id, meal_id, write=True)
        if meal.is_deleted:
            return
        if meal.revision != expected_revision:
            raise HTTPException(409, 'The meal has changed. Reload it before deleting.')
        self._apply_items(mission_id, meal, [], self._active_items(meal.id))
        meal.is_deleted = True
        meal.revision += 1
        self.session.add(meal)

    def list_meals(self, mission_id, member_id, day, page, per_page):
        _, actor = self._access(mission_id, {'astronaut', 'flight_surgeon', 'nutritionist'})
        if actor.role == 'nutritionist' and not self.user.is_nutritionist:
            raise HTTPException(403, 'A nutritionist profile is required')
        if actor.role == 'flight_surgeon':
            self._require_physician()
        if member_id is not None:
            self._meal_access(mission_id, member_id)
        elif actor.role == 'astronaut':
            member_id = actor.id
        statement = select(MealLog).where(MealLog.mission_id == mission_id, MealLog.is_deleted == False)
        if member_id is not None:
            statement = statement.where(MealLog.mission_member_id == member_id)
        if day:
            start = datetime.combine(day, time.min, tzinfo=timezone.utc)
            statement = statement.where(MealLog.consumed_at >= start, MealLog.consumed_at < start + timedelta(days=1))
        result = self._page(statement.order_by(MealLog.consumed_at.desc(), MealLog.id.desc()), page, per_page)
        result['data'] = [self._meal_response(meal) for meal in result['data']]
        return result

    def daily(self, mission_id, member_id, day):
        self._meal_access(mission_id, member_id)
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        meals = self.session.exec(select(MealLog).where(MealLog.mission_id == mission_id, MealLog.mission_member_id == member_id,
            MealLog.is_deleted == False, MealLog.consumed_at >= start, MealLog.consumed_at < start + timedelta(days=1)).order_by(MealLog.consumed_at, MealLog.id)).all()
        items = [item for meal in meals for item in self._active_items(meal.id)]
        return {'day': day, 'timezone': 'UTC', 'meals': [self._meal_response(meal) for meal in meals], 'totals': total_items(items)}
