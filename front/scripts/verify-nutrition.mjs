import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { chromium } from 'playwright';

const bundle = buildSync({ stdin: { contents: `import React from 'react';import {createRoot} from 'react-dom/client';import Nutrition from './src/Nutrition.jsx';const request=async(path,options={})=>{const response=await fetch('http://nutrition.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});if(response.status===204)return null;const data=await response.json();if(!response.ok){const error=new Error(data.detail);error.status=response.status;throw error;}return data;};createRoot(document.getElementById('root')).render(<Nutrition request={request} mission={{id:1}} members={[{id:2,user_id:3,role:'astronaut'}]} names={()=>'Ada'} role="flight_surgeon" physician={true} currentUserId={1} canManageCatalog={true}/>);`, loader: 'jsx', resolveDir: process.cwd() }, bundle: true, write: false, format: 'iife', loader: { '.css': 'empty' } }).outputFiles[0].text;
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome' });
try {
  const page = await browser.newPage();
  const products = [
    { id: 1, name: 'Freeze dried meal', category: 'food', is_plain_water: false, preservation_method: 'freeze_dried', physical_form: 'solid', reference_quantity: '100', reference_unit: 'g', reference_basis: 'stored', unit_equivalences: [], energy_kcal: '400', protein_g: '20', carbohydrate_g: '60', fat_g: '10', fiber_g: null, sodium_mg: null, preparation_method: 'rehydrate', preparation_water_ml: '250', is_active: true },
    { id: 2, name: 'Water', category: 'beverage', is_plain_water: true, preservation_method: 'natural_form', physical_form: 'liquid', reference_quantity: '100', reference_unit: 'ml', reference_basis: 'stored', unit_equivalences: [], energy_kcal: '0', protein_g: '0', carbohydrate_g: '0', fat_g: '0', fiber_g: '0', sodium_mg: '0', preparation_method: 'ready_to_consume', preparation_water_ml: null, is_active: true },
  ];
  const expiration = days => new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
  const lots = [
    { id: 1, mission_id: 1, food_product_id: 1, product_name: 'Freeze dried meal', lot_code: 'Late', expiration_date: expiration(30), initial_quantity: '500', remaining_quantity: '500', stock_unit: 'g', stock_basis: 'stored', is_expired: false, is_depleted: false, is_expiring_soon: false, expiration_warning_days: 7 },
    { id: 2, mission_id: 1, food_product_id: 1, product_name: 'Freeze dried meal', lot_code: 'Early', expiration_date: expiration(10), initial_quantity: '500', remaining_quantity: '500', stock_unit: 'g', stock_basis: 'stored', is_expired: false, is_depleted: false, is_expiring_soon: false, expiration_warning_days: 7 },
    { id: 3, mission_id: 1, food_product_id: 2, product_name: 'Water', lot_code: 'Water lot', expiration_date: expiration(30), initial_quantity: '5000', remaining_quantity: '5000', stock_unit: 'ml', stock_basis: 'stored', is_expired: false, is_depleted: false, is_expiring_soon: false, expiration_warning_days: 7 },
  ];
  const totals = { nutrients: Object.fromEntries(['energy_kcal', 'protein_g', 'carbohydrate_g', 'fat_g', 'fiber_g', 'sodium_mg'].map(key => [key, 0])), partial: {}, beverage_volume_ml: 0, plain_water_volume_ml: 0, preparation_water_used_ml: 0 };
  const submissions = [];
  await page.route('http://nutrition.test/**', async route => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'POST' && url.pathname.endsWith('/meal-logs')) {
      submissions.push(route.request().postDataJSON());
      if (submissions.length === 1) {
        lots[1].remaining_quantity = '0'; lots[1].is_depleted = true;
        await route.fulfill({ status: 409, json: { detail: 'Insufficient stock. Refresh the available lots.' } });
      } else await route.fulfill({ status: 201, json: { id: 1 } });
    } else if (url.pathname.endsWith('/food-products')) await route.fulfill({ json: { data: products, pagination: { has_next: false } } });
    else if (url.pathname.endsWith('/food-lots')) await route.fulfill({ json: { data: lots, pagination: { has_next: false } } });
    else if (url.pathname.endsWith('/nutrition/daily')) await route.fulfill({ json: { day: url.searchParams.get('day'), timezone: 'UTC', meals: [], totals } });
    else throw Error('Unexpected request: ' + url);
  });
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: bundle });
  await page.getByRole('button', { name: 'Consumption', exact: true }).click();
  await page.getByRole('button', { name: 'Record meal', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Add item', exact: true }).click();
  await dialog.getByLabel('Product 1', { exact: true }).selectOption('1');
  assert.equal(await dialog.getByLabel('Lot 1', { exact: true }).inputValue(), '2');
  await dialog.getByLabel('Consumed quantity 1', { exact: true }).fill('50');
  await dialog.getByLabel('Stock quantity used 1 (g)', { exact: true }).fill('60');
  await dialog.getByLabel('Preparation water used 1 (mL)', { exact: true }).fill('125');
  await dialog.getByLabel('Preparation water lot 1', { exact: true }).selectOption('3');
  await dialog.getByRole('button', { name: 'Add water', exact: true }).click();
  assert.equal(await dialog.getByLabel('Consumed unit 2', { exact: true }).inputValue(), 'ml');
  await dialog.getByLabel('Notes', { exact: true }).fill('Preserve this meal');
  await dialog.getByRole('button', { name: 'Save meal', exact: true }).click();
  await dialog.getByRole('alert').getByText('Insufficient stock. Refresh the available lots.').waitFor();
  assert.equal(await dialog.getByLabel('Notes', { exact: true }).inputValue(), 'Preserve this meal');
  assert.equal(await dialog.getByLabel('Consumed quantity 1', { exact: true }).inputValue(), '50');
  assert.equal(await dialog.getByLabel('Stock quantity used 1 (g)', { exact: true }).inputValue(), '60');
  await dialog.getByLabel('Lot 1', { exact: true }).selectOption('1');
  await dialog.getByRole('button', { name: 'Save meal', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert.equal(submissions[1].items[0].stock_quantity_used, '60');
  assert.equal(submissions[1].items[0].preparation_water_lot_id, 3);
  assert.equal(submissions[1].items[1].consumed_quantity, '250');
  assert.equal(submissions[1].items[1].consumed_unit, 'ml');
  console.log('Nutrition item selection, FEFO, Add water, stock conflict recovery and preserved fields passed.');
} finally { await browser.close(); }
