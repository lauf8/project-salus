import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { chromium } from 'playwright';

const bundle = buildSync({ stdin: { contents: `import React from 'react';import {createRoot} from 'react-dom/client';import ClinicalRecords,{ActiveHealthBanner} from './src/ClinicalRecords.jsx';const root=createRoot(document.getElementById('root'));const request=async(path,options={})=>{const response=await fetch('http://clinical.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});const data=await response.json();if(!response.ok)throw new Error(data.detail);return data;};window.renderClinical=doctor=>root.render(<><ActiveHealthBanner request={request} user={{id:2}} enabled={!doctor} onOpen={()=>{}}/><ClinicalRecords key={String(doctor)} request={request} astronautId={2} missionId={1} canResolve={doctor} users={[{id:2,name:'Synthetic Astronaut'},{id:1,name:'Synthetic Physician'}]}/></>);window.renderClinical(false);`, loader: 'jsx', resolveDir: process.cwd() }, bundle: true, write: false, format: 'iife', loader: { '.css': 'empty' } }).outputFiles[0].text;
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [], mutations = [];
  page.on('pageerror', error => errors.push(error.message));
  let occurrences = [], medications = [], assessments = [];
  const report = { cutoff: new Date().toISOString(), mission_day: 5, disease_probability: null, measurements: [], active_alerts: [], active_occurrences: [], medication_uses: [], limitations: ['No validated individual disease prediction model is configured.'] };
  const paged = data => ({ data, pagination: { total: data.length, total_pages: 1, has_next: false } });
  await page.route('http://clinical.test/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname, method = route.request().method();
    const body = () => route.request().postDataJSON();
    if (method === 'POST') mutations.push({ path, body: body() });
    if (path.endsWith('/icd10')) return route.fulfill({ json: paged([{ code: 'R51', name: 'Headache', selectable: true }]) });
    if (path === '/v1/medicines') return route.fulfill({ json: paged([{ id: 7, name: 'Synthetic medication' }]) });
    if (path.endsWith('/clinical-report')) return route.fulfill({ json: report });
    if (path.endsWith('/recover')) {
      occurrences[0] = { ...occurrences[0], ...body(), status: 'recovered', resolved_by_user_id: 1 };
      return route.fulfill({ json: occurrences[0] });
    }
    if (path.endsWith('/occurrences')) {
      if (method === 'POST') { occurrences.push({ id: 1, ...body(), astronaut_id: 2, status: 'active', recorded_at: new Date().toISOString(), recorded_by_user_id: 2 }); return route.fulfill({ json: occurrences[0] }); }
      return route.fulfill({ json: paged(url.searchParams.get('active') === 'true' ? occurrences.filter(row => row.status === 'active') : occurrences) });
    }
    if (path.endsWith('/medication-uses')) {
      if (method === 'POST') { medications.push({ id: 1, ...body(), astronaut_id: 2, medicine_name: 'Synthetic medication', recorded_at: new Date().toISOString(), recorded_by_user_id: 2 }); return route.fulfill({ json: medications[0] }); }
      return route.fulfill({ json: paged(medications) });
    }
    if (path.endsWith('/review')) { assessments[0] = { ...assessments[0], status: body().decision, review_note: body().note, reviewed_by_user_id: 1 }; return route.fulfill({ json: assessments[0] }); }
    if (path.endsWith('/assessments')) {
      if (method === 'POST') { assessments.push({ id: 1, status: 'pending', report: { ...report, generation_status: 'insufficient_evidence', hypotheses: [], sources: [] }, created_at: new Date().toISOString() }); return route.fulfill({ json: assessments[0] }); }
      return route.fulfill({ json: paged(assessments) });
    }
    throw new Error(`Unhandled request ${method} ${path}`);
  });
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: bundle });
  await page.getByRole('button', { name: 'Report a health problem', exact: true }).click();
  await page.getByLabel('Search WHO ICD-10 in English').fill('headache');
  await page.getByLabel('WHO ICD-10 code', { exact: true }).selectOption('R51');
  await page.getByLabel('Description', { exact: true }).fill('Synthetic headache report');
  await page.getByLabel('Symptoms', { exact: true }).fill('Synthetic head pain');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByLabel('Active health problems').waitFor();
  assert.equal(await page.getByRole('button', { name: 'Confirm recovery' }).count(), 0);
  await page.getByRole('button', { name: 'Record medication taken', exact: true }).click();
  await page.getByLabel('Medication', { exact: true }).selectOption('7');
  await page.getByLabel('Dose and route').fill('Synthetic dose');
  await page.getByLabel('Reason', { exact: true }).fill('Synthetic headache');
  await page.getByLabel('Who instructed you to take it?').fill('Synthetic Physician');
  await page.getByLabel('Related health problem (optional)').selectOption('1');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByText('Medication consumption history (1)', { exact: true }).click();
  await page.getByText('Reason: Synthetic headache · Directed by: Synthetic Physician', { exact: true }).waitFor();
  await page.evaluate(() => window.renderClinical(true));
  await page.getByRole('button', { name: 'Confirm recovery' }).click();
  await page.getByLabel('Recovery assessment').fill('Synthetic recovery verified');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('heading', { name: /Headache · recovered/ }).waitFor();
  await page.getByRole('button', { name: 'Generate NASA health assessment' }).click();
  await page.getByText(/NASA health assessment #1 · pending/).click();
  await page.getByRole('button', { name: 'Review for astronaut delivery' }).click();
  await page.getByLabel('Clinical review and instructions').fill('Reviewed synthetic assessment');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByText(/NASA health assessment #1 · approved/).waitFor();
  await page.evaluate(() => window.renderClinical(false));
  await page.getByRole('button', { name: 'Report a health problem', exact: true }).waitFor();
  assert.equal(await page.getByLabel('Active health problems').count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Confirm recovery' }).count(), 0);
  assert.equal(mutations.length, 5);
  assert.equal(mutations[1].body.instructed_by, 'Synthetic Physician');
  assert.equal(mutations[1].body.occurrence_id, 1);
  assert.deepEqual(errors, []);
  console.log('Clinical browser flow passed: WHO selection, persistent active problem, medication consumption, physician recovery, NASA review, mobile layout.');
} finally { await browser.close(); }
