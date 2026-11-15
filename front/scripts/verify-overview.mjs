import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {existsSync} from 'node:fs';
import {chromium} from 'playwright';

const portugueseWords = /\b(não|são|saúde|missão|missões|astronauta|tripulação|médico|equipe|risco|riscos|alerta|alertas|dados|previsão|recomendação|sono|fadiga|humor|para|com|uma|que)\b/i;
const server = await createServer({logLevel: 'error', server: {port: 0, host: '127.0.0.1'}});
await server.listen();
const baseUrl = server.resolvedUrls.local[0].replace(/\/$/, '');
const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || ['/opt/pw-browsers/chromium', '/usr/bin/google-chrome'].find(existsSync)});

async function loadAll(page) {
  const height = await page.evaluate(() => document.body.scrollHeight);
  for (let y = 0; y < height; y += 500) {
    await page.evaluate(top => window.scrollTo(0, top), y);
    await page.waitForTimeout(40);
  }
  await page.waitForFunction(() => [...document.images].every(image => image.complete));
}

try {
  for (const viewport of [{width: 1400, height: 900}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.goto(`${baseUrl}/overview`);
    await page.getByRole('heading', {level: 1, name: 'To predict is to protect.'}).waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.lang), 'en');
    for (const name of ['Health care in space is still reactive.', 'Four data streams. One continuous view.', 'How Salus anticipates risk.', 'Alert the medical team before it becomes a problem.', 'Every mission makes the next one safer.']) {
      await page.getByRole('heading', {name}).waitFor();
    }
    await loadAll(page);
    const broken = await page.evaluate(() => [...document.images].filter(image => !image.naturalWidth).map(image => image.src));
    assert.deepEqual(broken, []);
    const text = await page.evaluate(() => [document.title, document.body.innerText, ...[...document.querySelectorAll('[alt], [aria-label], title, desc, meta[name="description"]')].map(element => element.getAttribute('alt') || element.getAttribute('aria-label') || element.getAttribute('content') || element.textContent)].join('\n'));
    assert.doesNotMatch(text, /[À-ÿ]/);
    assert.doesNotMatch(text, portugueseWords);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), viewport.width);
    await page.getByRole('button', {name: /Enlarge pending rest-period review/}).click();
    await page.getByRole('dialog').getByRole('heading', {name: 'Pending rest-period review'}).waitFor();
    await page.getByRole('button', {name: 'Close screenshot'}).click();
    assert.deepEqual(errors, []);
    await page.close();
  }

  const tour = await browser.newPage({viewport: {width: 1400, height: 900}});
  await tour.goto(`${baseUrl}/overview?tour=7`);
  await tour.waitForFunction(() => document.getElementById('closing') && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2, null, {timeout: 12000});
  await tour.close();

  console.log('Overview landing page verified: English text, images, layout and narrated tour.');
} finally {
  await browser.close();
  await server.close();
}
