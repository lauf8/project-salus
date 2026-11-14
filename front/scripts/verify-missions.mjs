import assert from 'node:assert/strict';
import { buildSync } from 'esbuild';
import { chromium } from 'playwright';

const bundle = buildSync({ stdin: { contents: `import React from 'react'; import {createRoot} from 'react-dom/client'; import Form from './src/MissionCreateForm.jsx'; createRoot(document.getElementById('root')).render(<Form request={async(path,options={})=>{const response=await fetch('http://mission.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});const data=await response.json();if(!response.ok){const error=new Error(data.detail);error.status=response.status;throw error;}return data;}} onSaved={()=>{window.saved=true;}} onClose={()=>{window.closedForm=true;}}/>);`, loader: 'jsx', resolveDir: process.cwd() }, bundle: true, write: false, format: 'iife' }).outputFiles[0].text;
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome' });
try {
  const page = await browser.newPage();
  let available = [{ id: 1, name: 'Explorer', status: 'available', maximum_crew_capacity: 2 }, { id: 2, name: 'Busy ship', status: 'in_use' }], posts = [];
  await page.route('http://mission.test/**', async route => {
    if (new URL(route.request().url()).pathname === '/v1/users/') {
      const query = new URL(route.request().url()).searchParams.get('search').toLowerCase();
      const people = [{ id: 101, name: 'Alice Alpha', email: 'alice@example.com', is_astronaut: true }, { id: 102, name: 'Bruno Beta', email: 'bruno@example.com', is_astronaut: true }];
      await route.fulfill({ json: { data: people.filter(user => user.name.toLowerCase().includes(query)), pagination: { has_next: false } } });
    } else if (route.request().method() === 'POST') {
      posts.push(route.request().postDataJSON());
      if (posts.length === 1) { available = [{ id: 3, name: 'Voyager', status: 'available', maximum_crew_capacity: 3 }]; await route.fulfill({ status: 409, json: { detail: 'Spacecraft is no longer available.' } }); }
      else await route.fulfill({ status: 201, json: { id: 1 } });
    } else await route.fulfill({ json: { data: available, pagination: { has_next: false } } });
  });
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: bundle });
  await page.getByRole('option', { name: 'Explorer', exact: true }).waitFor({ state: 'attached' });
  assert.equal(await page.getByRole('option', { name: 'Busy ship' }).count(), 0);
  assert.equal(await page.getByRole('button', { name: 'Save', exact: true }).isDisabled(), true);
  await page.getByLabel('Mission name').fill('Preserved mission');
  await page.getByLabel('Planned launch').fill('2026-12-20T12:00');
  await page.getByLabel('Planned crew size', { exact: true }).fill('2');
  await page.getByLabel('Spacecraft', { exact: true }).selectOption('1');
  await page.getByLabel('Planned crew size').fill('3');
  assert.equal(await page.getByRole('button', { name: 'Save', exact: true }).isDisabled(), true);
  await page.getByLabel('Planned crew size').fill('2');
  await page.getByLabel('Search astronauts by name').fill('Alice');
  await page.getByRole('button', { name: 'Add Alice Alpha' }).click();
  await page.getByLabel('Search astronauts by name').fill('Bruno');
  await page.getByRole('button', { name: 'Add Bruno Beta' }).click();
  assert.equal(await page.getByLabel('Search astronauts by name').isDisabled(), true);
  await page.getByRole('button', { name: 'Remove Bruno Beta' }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByRole('alert').getByText('Spacecraft is no longer available.').waitFor();
  await page.getByRole('option', { name: 'Voyager' }).waitFor({ state: 'attached' });
  assert.equal(await page.getByLabel('Mission name').inputValue(), 'Preserved mission');
  assert.equal(await page.getByLabel('Planned launch').inputValue(), '2026-12-20T12:00');
  assert.equal(await page.getByLabel('Spacecraft', { exact: true }).inputValue(), '');
  await page.getByLabel('Spacecraft', { exact: true }).selectOption('3');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await page.waitForFunction(() => window.saved && window.closedForm);
  assert.equal(posts[1].spacecraft_id, 3);
  assert.equal(posts[1].crew_size, 2);
  assert.deepEqual(posts[1].astronaut_ids, [101]);
  available = [];
  await page.setContent('<div id="root"></div>');
  await page.addScriptTag({ content: bundle });
  await page.getByText('No spacecraft available.').waitFor();
  assert.equal(await page.getByRole('button', { name: 'Save', exact: true }).isDisabled(), true);
  console.log('Mission form validation, conflict recovery, preserved fields, and empty availability passed.');
} finally { await browser.close(); }
