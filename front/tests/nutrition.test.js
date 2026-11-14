import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { buildSync } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { equivalents, nutritionPages, previewNutrition, referenceAmount, usableLots } from '../src/nutrition.js';

const require = createRequire(import.meta.url);
function load(path) {
  const output = buildSync({ entryPoints: [path], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'], loader: { '.css': 'empty' } }).outputFiles[0].text;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', output)(require, module, module.exports);
  return module.exports;
}
const { MealForm, ProductForm, Inventory } = load('src/Nutrition.jsx');
const food = { id: 1, name: 'Freeze dried meal', category: 'food', is_plain_water: false, preservation_method: 'freeze_dried', physical_form: 'solid', reference_quantity: '100', reference_unit: 'g', reference_basis: 'stored', unit_equivalences: [{ unit: 'ml', basis: 'prepared', quantity_per_reference: '250' }], energy_kcal: '400', protein_g: '20', carbohydrate_g: '60', fat_g: '10', fiber_g: null, sodium_mg: '100', preparation_method: 'rehydrate', preparation_water_ml: '250', is_active: true };
const water = { ...food, id: 2, name: 'Water', category: 'beverage', is_plain_water: true, physical_form: 'liquid', reference_unit: 'ml', unit_equivalences: [], energy_kcal: '0', protein_g: '0', carbohydrate_g: '0', fat_g: '0', fiber_g: '0', sodium_mg: '0', preparation_method: 'ready_to_consume' };
const juice = { ...water, id: 3, name: 'Juice', is_plain_water: false, energy_kcal: '40', carbohydrate_g: '10' };
const lots = [
  { id: 1, food_product_id: 1, product_name: food.name, expiration_date: '2026-11-20', lot_code: 'Late', initial_quantity: '500', remaining_quantity: '500', stock_unit: 'g', stock_basis: 'stored' },
  { id: 2, food_product_id: 1, product_name: food.name, expiration_date: '2026-11-16', lot_code: 'Early', initial_quantity: '500', remaining_quantity: '500', stock_unit: 'g', stock_basis: 'stored' },
  { id: 3, food_product_id: 1, product_name: food.name, expiration_date: '2026-11-01', lot_code: 'Expired', initial_quantity: '500', remaining_quantity: '500', stock_unit: 'g' },
  { id: 4, food_product_id: 1, product_name: food.name, expiration_date: '2026-11-15', lot_code: 'Empty', initial_quantity: '500', remaining_quantity: '0', stock_unit: 'g' },
];

test('FEFO suggestions exclude expired and depleted lots using the UTC meal day', () => {
  assert.deepEqual(usableLots(lots, 1, '2026-11-14T12:00:00Z').map(row => row.id), [2, 1]);
  assert.deepEqual(usableLots(lots, 1, '2026-11-16T23:30:00-03:00').map(row => row.id), [1]);
  assert.deepEqual(usableLots(lots, 999, '2026-11-14T12:00:00Z'), []);
});

test('nutrition preview separates consumption from withdrawals and preparation water', () => {
  const totals = previewNutrition([
    { food_product_id: 1, consumed_quantity: '50', consumed_unit: 'g', consumed_basis: 'stored', preparation_water_used_ml: '125' },
    { food_product_id: 3, consumed_quantity: '150', consumed_unit: 'ml', consumed_basis: 'stored', stock_quantity_used: '200' },
    { food_product_id: 2, consumed_quantity: '250', consumed_unit: 'ml', consumed_basis: 'stored' },
  ], [food, water, juice]);
  assert.equal(totals.nutrients.energy_kcal, 260);
  assert.equal(totals.nutrients.protein_g, 10);
  assert.equal(totals.beverage_volume_ml, 400);
  assert.equal(totals.plain_water_volume_ml, 250);
  assert.equal(totals.preparation_water_used_ml, 125);
  assert.equal(totals.partial.fiber_g, true);
  assert.equal(totals.partial.protein_g, false);
});

test('unit conversion requires registered basis and unit and never assumes g equals ml', () => {
  assert.throws(() => referenceAmount(food, 'ml', 'stored'), /No registered equivalence/);
  assert.equal(referenceAmount(food, 'ml', 'prepared'), 250);
  const totals = previewNutrition([{ food_product_id: 1, consumed_quantity: '125', consumed_unit: 'ml', consumed_basis: 'prepared' }], [food]);
  assert.equal(totals.nutrients.energy_kcal, 200);
  assert.equal(equivalents(food).length, 2);
  const invalid = previewNutrition([{ food_product_id: 1, consumed_quantity: '125', consumed_unit: 'ml', consumed_basis: 'stored' }], [food]);
  assert.equal(invalid.errors.length, 1);
});

test('existing meal previews retain snapshot nutrients after catalog edits', () => {
  const totals = previewNutrition([{ id: 10, _snapshot: food, food_product_id: 1, consumed_quantity: '50', consumed_unit: 'g', consumed_basis: 'stored' }], [{ ...food, energy_kcal: '999' }]);
  assert.equal(totals.nutrients.energy_kcal, 200);
  const waterTotals = previewNutrition([{ food_product_id: 2, consumed_quantity: '100', consumed_unit: 'ml', consumed_basis: 'stored' }], [water]);
  assert.equal(waterTotals.nutrients.energy_kcal, 0);
  assert.equal(waterTotals.partial.energy_kcal, false);
});

test('product form distinguishes preservation from physical form and keeps unknown and zero nutrition', () => {
  const html = renderToStaticMarkup(React.createElement(ProductForm, { request: async () => {}, initial: water, onClose() {}, onSaved() {} }));
  for (const title of ['Preservation method', 'Physical form', 'Nutrition refers to', 'Registered equivalences', 'Plain water']) assert.ok(html.includes(title));
  assert.match(html, /value="0"/);
  assert.match(html, /Enter 0 when the value is known to be zero/);
});

test('meal form retains existing item values and renders water, lots, consumed and stock quantities separately', () => {
  const initial = { id: 1, mission_member_id: 2, consumed_at: '2026-11-14T12:00:00Z', meal_type: 'lunch', notes: 'Preserved note', revision: 1, items: [{ id: 10, food_product_id: 1, lot_id: 2, consumed_quantity: '50', consumed_unit: 'g', consumed_basis: 'stored', stock_quantity_used: '60', preparation_water_used_ml: '125', preparation_water_lot_id: null, product_snapshot: food }] };
  const html = renderToStaticMarkup(React.createElement(MealForm, { request: async () => {}, base: '/v1/missions/1', products: [food, water], lots, members: [{ id: 2, user_id: 3 }], names: () => 'Astronaut', initial, onClose() {}, onSaved() {}, onRefresh() {} }));
  for (const text of ['Add water', 'Consumed quantity 1', 'Stock quantity used 1', 'Preparation water used 1', 'Early', 'Suggested', 'Preserved note', 'value="50"', 'value="60"']) assert.ok(html.includes(text), text);
  assert.ok(html.indexOf('Early') < html.indexOf('Late'));
});

test('inventory shows initial, balance, expiration and separate lot codes', () => {
  const html = renderToStaticMarkup(React.createElement(Inventory, { request: async () => {}, base: '/v1/missions/1', products: [food], lots: lots.slice(0, 2), canManage: true, onRefresh() {} }));
  for (const text of ['INITIAL', 'BALANCE', 'EXPIRATION', 'Late', 'Early', 'Movements', 'Add lot']) assert.ok(html.includes(text));
});

test('nutrition pagination preserves filter parameters on every page', async () => {
  const paths = [];
  const result = await nutritionPages(async path => { paths.push(path); return { data: [paths.length], pagination: { has_next: paths.length < 2 } }; }, '/v1/missions/1/food-lots', { status: 'usable' });
  assert.deepEqual(result, [1, 2]);
  assert.ok(paths.every(path => path.includes('status=usable')));
  assert.ok(paths[1].includes('page=2'));
});
