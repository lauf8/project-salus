import assert from 'node:assert/strict';
import {buildSync} from 'esbuild';
import {chromium} from 'playwright';

const props = {mission: {id: 1, name: 'Synthetic food mission', crew_size: 2, planned_launch_at: '2026-11-01T00:00:00Z'}, members: [{id: 1, user_id: 1, role: 'mission_admin'}, {id: 2, user_id: 2, role: 'astronaut'}]};
const bundle = buildSync({stdin: {contents: `import React from 'react';import {createRoot} from 'react-dom/client';import Component from './src/MissionRisks.jsx';const request=async(path,options={})=>{const multipart=options.body instanceof FormData;const response=await fetch('http://risks.test'+path,{...options,body:options.body?(multipart?options.body:JSON.stringify(options.body)):undefined});const data=await response.json();if(!response.ok)throw new Error(data.detail);return data;};createRoot(document.getElementById('root')).render(<Component request={request} {...${JSON.stringify(props)}} names={id=>'User #'+id}/>);`, loader: 'jsx', resolveDir: process.cwd()}, bundle: true, write: false, format: 'iife', loader: {'.css': 'empty'}}).outputFiles[0].text;
const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome'});
try {
  const page = await browser.newPage();
  let plans = [], occurrences = [], documents = [], actionHistory = [], processCalls = 0, uploads = 0, canManage = true;
  const mutations = [];
  const source = {id: 7, title: 'Synthetic NASA food procedure', page: 2, origin: 'NASA', revision: '1', source_url: 'https://www.nasa.gov/synthetic-fixture', content: 'Synthetic inventory evidence for UI verification.'};
  const item = {food_product_id: 1, food_name: 'Synthetic rice', current_balance: '2', quantity_unit: 'food reference portions', reference: {quantity: '100', unit: 'g'}, first_shortage_date: '2026-11-16', daily_rate: '2', planned_daily_rate: '2', observed_daily_rate: null, consumption_source: 'planned demand', consumption_window: {start: '2026-11-07T00:00:00Z', end: '2026-11-14T00:00:00Z'}, missing_data: [], state: 'risk', history: {frequency: '1 of 2 comparable missions with sufficient data', eligible_missions: 3, criteria: 'Same food, comparable crew and exposure.', occurrences: []}, daily_projection: [{date: '2026-11-15', opening_balance: '2', demand: '2', expired: '0', unmet: '0', balance: '0'}]};
  const alert = {id: 1, food_product_id: 1, evaluation_id: 1, assessment: item, severity: 'critical', due_at: '2026-11-16T00:00:00Z', responsible_user_id: 2, status: 'open', updated_at: '2026-11-14T00:00:00Z', guidance: {state: 'pending', action: 'Verify inventory.', sources: [], documentary_evidence: false}};
  const state = () => ({can_manage: canManage, evaluation: plans.length ? {id: 1, evaluated_at: '2026-11-14T00:00:00Z', rule_version: 'food-fefo-v1', state: 'evaluated', horizon: '2026-11-22T00:00:00Z', results: {missing_data: [], items: [item]}} : null, alerts: plans.length ? [alert] : [], categories: {sleep_fatigue: {implemented: false, missing: ['sleep periods'], clinical_review_required: true}}});
  await page.route('http://risks.test/**', async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    if (path === '/v1/food-products') return route.fulfill({json: {data: [{id: 1, name: 'Synthetic rice', reference_unit: 'g'}], pagination: {has_next: false}}});
    if (path === '/v1/missions/1/risks/health') return route.fulfill({json: {state: 'available', alerts: [{id: 90, astronaut_id: 2, indicator: 'blood_glucose', severity: 'critical', status: 'open', reason: 'Synthetic low glucose screening signal.', collected_at: '2026-11-14T00:00:00Z', rule_version: 'simulation-v2', context: {title: 'Low blood glucose / hypoglycemia signal', next_step: 'Review with the assigned physician.', source_url: 'https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/low-blood-glucose-hypoglycemia', source_title: 'NIDDK'}}]}});
    if (path === '/v1/missions/1/risks') return route.fulfill({json: state()});
    if (path.endsWith('/plans')) {
      if (method === 'POST') {const data = route.request().postDataJSON();mutations.push(data);plans = [{id: plans.length + 1, ...data}];}
      return route.fulfill({json: method === 'POST' ? plans[0] : plans});
    }
    if (path.endsWith('/occurrences')) {
      if (method === 'POST') {occurrences.push({id: 1, ...route.request().postDataJSON(), recorded_at: '2026-11-14T00:00:00Z', confirmed_at: null});}
      return route.fulfill({json: method === 'POST' ? occurrences[0] : occurrences});
    }
    if (path.endsWith('/confirm')) {occurrences[0].confirmed_at = '2026-11-14T00:00:00Z';return route.fulfill({json: occurrences[0]});}
    if (path === '/v1/risk-documents') {
      if (method === 'POST') {assert.match(route.request().headers()['content-type'], /multipart\/form-data/);uploads++;documents = [{id: 1, title: 'Synthetic NASA food procedure', revision: '1', source_origin: 'NASA', indexing_status: 'queued', reindex_required: true}];}
      return route.fulfill({json: method === 'POST' ? documents[0] : documents});
    }
    if (path.endsWith('/process')) {processCalls++;documents[0] = {...documents[0], indexing_status: processCalls === 1 ? 'failed' : 'completed', indexing_error: processCalls === 1 ? 'Ollama unavailable; retry indexing.' : null, embedding_model: 'all-minilm', embedding_dimension: 384, reindex_required: false};return route.fulfill({json: documents[0]});}
    if (path.endsWith('/search')) return route.fulfill({json: [source]});
    if (path.endsWith('/guidance')) {alert.guidance = {state: 'documented', action: 'Verify usable lots with mission control.', documentary_evidence: true, sources: [source], generated_action: 'Verify usable lots with mission control.', review_state: 'pending_review'};return route.fulfill({json: alert});}
    if (path.endsWith('/actions')) {
      if (method === 'POST') {const action = route.request().postDataJSON();mutations.push(action);actionHistory.push({id: actionHistory.length + 1, actor_user_id: 2, recorded_at: '2026-11-14T00:00:00Z', ...action});alert.status = {read: 'acknowledged', execute: 'executed', resolve: 'resolved'}[action.action] || alert.status;alert.updated_at = `2026-11-14T00:00:0${actionHistory.length}Z`;if (action.action === 'resolve') alert.outcome = action.details;if(action.action === 'approve_guidance')alert.guidance.review_state='approved';}
      return route.fulfill({json: method === 'POST' ? alert : actionHistory});
    }
    if (path.endsWith('/evaluate')) return route.fulfill({json: {id: 1}});
    throw new Error(`Unhandled request ${method} ${path}`);
  });
  await page.setContent('<div id="root"></div>');await page.addScriptTag({content: bundle});
  await page.getByText('No assessment yet.', {exact: false}).waitFor();
  await page.getByRole('heading', {name: 'Low blood glucose / hypoglycemia signal'}).waitFor();
  await page.getByRole('button', {name: 'planning', exact: true}).click();
  await page.getByLabel('Expected mission end').fill('2026-11-22T00:00');
  await page.getByLabel('Inventory for this mission is complete').check();
  await page.getByLabel('Planned food 1').selectOption('1');
  await page.getByLabel('Quantity per day', {exact: true}).fill('100');
  await page.getByRole('button', {name: 'Save planning and evaluate'}).click();
  await page.waitForFunction(() => document.querySelector('h2')?.textContent === 'Mission risks');
  await page.getByRole('button', {name: 'alerts', exact: true}).click();
  await page.getByRole('button', {name: /Synthetic rice/}).click();
  await page.getByText('1 of 2 comparable missions with sufficient data', {exact: true}).first().waitFor();
  await page.getByRole('button', {name: 'Retrieve preventive guidance'}).click();
  await page.getByText(/passage #7 · page 2/).waitFor();
  await page.getByLabel('Record action').selectOption('approve_guidance');
  await page.getByLabel('Action / outcome details').fill('Approved operational inventory guidance');
  await page.getByRole('button', {name: 'Save action', exact: true}).click();
  await page.getByText('Approved operational inventory guidance', {exact: false}).waitFor();
  await page.getByLabel('Record action').selectOption('read');
  await page.getByLabel('Action / outcome details').fill('Read inventory procedure');
  await page.getByRole('button', {name: 'Save action', exact: true}).click();
  await page.getByText('Read inventory procedure', {exact: false}).waitFor();
  await page.getByRole('button', {name: 'documents', exact: true}).click();
  await page.getByLabel('Document title').fill('Synthetic NASA food procedure');
  await page.getByLabel('PDF (maximum 20 MiB)').setInputFiles({name: 'synthetic.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 synthetic UI fixture')});
  await page.getByRole('button', {name: 'Import PDF', exact: true}).click();
  await page.getByRole('button', {name: 'Index / reindex'}).click();
  await page.getByRole('button', {name: 'Retry processing'}).waitFor();
  await page.getByRole('button', {name: 'Retry processing'}).click();
  await page.getByText('384 dimensions', {exact: true}).waitFor();
  await page.getByLabel('Search passages').fill('food inventory');
  await page.getByRole('button', {name: 'Search evidence', exact: true}).click();
  await page.getByText(/passage #7 · page 2/).waitFor();
  await page.getByRole('button', {name: 'occurrences', exact: true}).click();
  await page.getByText('Register an observed occurrence', {exact: true}).click();
  await page.getByLabel('Occurrence food product', {exact: true}).selectOption('1');
  await page.getByLabel('Event time', {exact: true}).fill('2026-11-13T12:00');
  await page.getByLabel('Verifiable source URL').fill('https://www.nasa.gov/synthetic-event');
  await page.getByLabel('Description', {exact: true}).fill('Synthetic observed shortage');
  await page.getByLabel('Actions taken', {exact: true}).fill('Verified stock');
  await page.getByLabel('Outcome', {exact: true}).fill('Requested resupply');
  await page.getByRole('button', {name: 'Register unconfirmed event'}).click();
  await page.getByRole('button', {name: 'Confirm this occurrence'}).waitFor();
  assert.equal(occurrences[0].confirmed_at, null);
  await page.getByRole('button', {name: 'Confirm this occurrence'}).click();
  await page.getByText('Confirmed', {exact: false}).last().waitFor();
  canManage = false;
  await page.reload();await page.setContent('<div id="root"></div>');await page.addScriptTag({content: bundle});
  await page.getByRole('button', {name: /Synthetic rice/}).click();
  assert.equal(await page.getByRole('button', {name: 'planning', exact: true}).count(), 0);
  assert.equal(await page.getByRole('button', {name: 'Retrieve preventive guidance'}).count(), 0);
  assert.equal(await page.getByRole('option', {name: 'Record outcome and resolve'}).count(), 0);
  await page.getByLabel('Record action').selectOption('execute');
  await page.getByLabel('Action / outcome details').fill('Executed stock verification');
  await page.getByRole('button', {name: 'Save action', exact: true}).click();
  await page.getByText('Executed stock verification', {exact: false}).waitFor();
  assert.equal(uploads, 1);assert.equal(processCalls, 2);
  assert(mutations.some(row => row.action === 'execute'));
  console.log('Mission risks browser flow passed: planning, projection detail, history, citations, PDF upload/retry, confirmed occurrence and astronaut read/execution permissions. API responses are simulated.');
} finally {await browser.close();}
