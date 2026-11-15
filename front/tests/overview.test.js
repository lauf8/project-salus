import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {defaultTourSeconds, narratedTourSteps, tourDurationFromSearch, tourSchedule} from '../src/overview-tour.js';

const sources = ['src/Overview.jsx', 'src/bootstrap.jsx', 'src/overview-tour.js'].map(path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8'));
const portugueseWords = /\b(não|nao|são|saúde|missão|missões|astronauta|astronautas|tripulação|tripulante|médico|médica|equipe|risco|riscos|alerta|alertas|prever|proteger|dados|clima espacial|previsão|recomendação|recomendações|sono|fadiga|humor|uma|que)\b/i;

test('landing page source contains no Portuguese words or accented letters', () => {
  for (const source of sources) {
    const strings = source.match(/'[^'\n]*'|`[^`\n]*`|>[^<>{}\n]+</g) || [];
    for (const text of strings.map(value => value.replace(/https?:\/\/[^\s'`]+/g, ""))) {
      assert.doesNotMatch(text, /[À-ÿ]/, text);
      assert.doesNotMatch(text, portugueseWords, text);
    }
  }
});

test('narrated tour follows the narration order and ends on the closing line', () => {
  assert.deepEqual(narratedTourSteps.map(step => step.id), ['top', 'problem', 'data', 'prediction', 'alerts', 'learning', 'closing']);
  const schedule = tourSchedule(narratedTourSteps, 40);
  assert.equal(schedule[0].startSeconds, 0);
  for (let index = 1; index < schedule.length; index++) assert.ok(schedule[index].startSeconds > schedule[index - 1].startSeconds);
  assert.ok(schedule.at(-1).startSeconds < 40);
});

test('tour duration comes from the query string', () => {
  assert.equal(tourDurationFromSearch(''), null);
  assert.equal(tourDurationFromSearch('?tour'), defaultTourSeconds);
  assert.equal(tourDurationFromSearch('?tour=50'), 50);
  assert.equal(tourDurationFromSearch('?tour=abc'), defaultTourSeconds);
});
