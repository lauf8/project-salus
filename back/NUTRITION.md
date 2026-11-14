Food, hydration and mission inventory
====================================

Apply `alembic upgrade head` before starting the updated API. Migration `e8cd3456f708` adds the nutrition tables without modifying existing missions or memberships and registers Water as a beverage with known zero nutrients.

The interface includes a Food and beverages catalog and a Food and hydration tab within each mission. The mission section contains Inventory, Consumption and Catalog views. Consumption is selected by astronaut and UTC day. Meal timestamps are entered in the browser's local timezone and sent with an offset converted to UTC.

Units and nutritional references
-------------------------------

Quantities use decimal precision with six fractional digits. Supported units are `g`, `ml`, `serving`, `package` and `piece`. Every product declares `reference_quantity`, `reference_unit` and `reference_basis` (`stored` or `prepared`). Preservation method, physical form and preparation method are independent fields.

A unit equivalence declares `quantity_per_reference` for a specific unit and basis. Each entry represents exactly one nutritional reference. The reference unit and basis are automatically registered and must not be duplicated in the equivalence list. Unknown nutrients are null; known zero values remain zero.

For example, a food with a stored reference of 100 g can register an equivalence of 250 ml prepared. Consuming 125 ml prepared consumes half the reference, uses 50 g of stored stock, and contributes half the reference nutrients. No conversion is inferred between grams and milliliters or between stored and prepared products.

For a 100 ml beverage reference, an equivalence of 0.5 package stored describes a 200 ml package. Consuming 150 ml uses 0.75 package by default. Recording `stock_quantity_used: 1` withdraws the whole package while calculating nutrients for 150 ml. Explicit withdrawals cannot be smaller than the consumed equivalent.

Inventory and history
---------------------

Each lot has immutable initial quantity, unit, basis and expiration date. Different lot codes support multiple lots of the same product in one mission. Receipts, consumption and reversals are recorded in `food_stock_movements`; there are no destructive catalog or lot deletion endpoints. Catalog products can be deactivated.

Lot expiration is inclusive through its expiration date in UTC. A historical meal can use a lot that was valid on the meal's UTC date even if the lot has since expired. The UI suggests the usable lot with the earliest expiration. Set `FOOD_EXPIRATION_WARNING_DAYS` in the API environment to configure warnings; Docker Compose passes this setting with a default of 7 days.

All meal changes serialize through the mission lock, lock affected lots in ID order and apply conditional balance updates. A transaction contains the meal, item snapshots, debits and reversals. The balance cannot become negative or exceed its initial quantity. Updates reverse the prior active item withdrawals and apply the replacement quantities atomically. Previous item versions and stock movements remain stored. Deletion marks the meal deleted, retires its items and reverses withdrawals once.

`expected_revision` prevents stale updates and deletes. A repeated deletion does not restore stock twice. Optional `client_request_id` UUIDs prevent duplicate creation on retries; reusing a key with a different request returns HTTP 409. The frontend generates a request key for each meal form.

Item snapshots preserve the product's reference, equivalences, name and nutrient values. An update that retains an existing item's `id` uses that snapshot. Removing the item and adding a new one uses the current catalog. Memberships referenced by meal history cannot be deleted or have their role changed.

Hydration and partial totals
----------------------------

`includes_plain_water` is derived from actual consumed items. Beverage totals include plain water drunk. Plain water totals include only products marked `is_plain_water`. Preparation water is reported separately and is never automatically included in either drinking total.

Set `preparation_water_used_ml` on an item to report preparation water. If it came from mission stock, also set `preparation_water_lot_id` to a plain water lot; its stock withdrawal is linked to the meal item with purpose `preparation_water`. Leaving the lot null reports water without withdrawing mission stock.

Each item's nutrients are calculated from its consumed quantity and stored as a snapshot. Totals contain a separate `partial` flag for each nutrient. Unknown beverage or plain water volume is also flagged as partial when no ml equivalence exists. Known values are summed without treating unknown values as zero.

Permissions and endpoints
-------------------------

Authenticated users can read the catalog. Catalog writes reuse the physician and assigned mission administrator or flight surgeon requirement. Mission members can read mission inventory; mission administrators and authorized flight surgeons can register lots and inspect stock movements. Astronauts can access only their own meals, while authorized physicians assigned as flight surgeons can access their mission's astronaut records. Mission administrators do not automatically gain access to private consumption records.

- `GET`, `POST /v1/food-products`; `GET`, `PUT /v1/food-products/{id}`.
- `GET`, `POST /v1/missions/{id}/food-lots`; lot listing supports search, product, status and aware `consumed_at` filters.
- `GET /v1/missions/{id}/food-lots/{lot_id}/movements`.
- `GET`, `POST /v1/missions/{id}/meal-logs`; listing supports membership and UTC day filters.
- `GET`, `PUT`, `DELETE /v1/missions/{id}/meal-logs/{meal_id}`; updates require `expected_revision` in the body and deletion requires it in the query.
- `GET /v1/missions/{id}/nutrition/daily?mission_member_id=...&day=YYYY-MM-DD` returns meals and daily totals.

Validation
----------

Run `pytest tests/test_nutrition.py` for API, nutrition, decimal balance, history, permissions, expiry and retry tests. Run `NUTRITION_POSTGRES_TESTS=1 pytest tests/test_nutrition_postgres.py` for concurrent depletion and migration tests using isolated temporary PostgreSQL schemas. These checks retain existing database data.

In the frontend, run `npm test`, `npm run typecheck`, `npm run build` and `npm run test:nutrition:e2e`. The browser test checks dynamic meal items, earliest-expiration suggestions, Add water and field preservation after a simulated stock conflict.
