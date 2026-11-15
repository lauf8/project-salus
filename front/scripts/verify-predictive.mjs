import assert from 'node:assert/strict';
import {buildSync} from 'esbuild';
import {chromium} from 'playwright';

const props = {missions: [{id: 1, name: 'Synthetic predictive mission'}], spacecraft: [{id: 1, name: 'Synthetic vehicle'}], user: {id: 3, is_global_admin: false}};
const bundle = buildSync({stdin: {contents: `import React from 'react';import {createRoot} from 'react-dom/client';import Component from './src/PredictiveIntelligence.jsx';const request=async(path,options={})=>{const response=await fetch('http://predictive.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});const data=await response.json();if(!response.ok)throw new Error(data.detail);return data;};createRoot(document.getElementById('root')).render(<Component request={request} {...${JSON.stringify(props)}}/>);`, loader: 'jsx', resolveDir: process.cwd()}, bundle: true, write: false, format: 'iife', loader: {'.css': 'empty'}}).outputFiles[0].text;

const rulePrediction = {id: 11, domain: 'sleep', risk_type: 'sleep_fatigue_combined', title: 'Reduced sleep with increasing fatigue', prediction_kind: 'rule', kind_label: 'Rule-based risk', risk_level: 'moderate', score: 3.4, score_meaning: 'Largest absolute z-score. It measures deviation, not probability.', calibrated_probability: null, probability_valid: false, horizon_hours: 24,
  factors: [{indicator: 'sleep_duration', direction: 'decrease', z_score: -3.4, mean_7d: 320, baseline_mean: 450, baseline_source: 'individual_history', unit: 'min', relative_contribution: 0.55}, {indicator: 'fatigue', direction: 'increase', z_score: 2.8, mean_7d: 8, baseline_mean: 3.5, baseline_source: 'individual_history', unit: '0-10', relative_contribution: 0.45}],
  data_quality: {}, uncertainty: {level: 'high', note: 'Small baselines widen uncertainty.'}, evidence: {excluded_actions: [{action_code: 'additional_vital_sign_monitoring', reason: 'contraindicated', details: ['A critical clinical alert is active.']}]}};
const mlPrediction = {id: 12, domain: 'sleep', risk_type: 'elevated_fatigue_24h', title: 'Elevated fatigue in the next 24 hours', prediction_kind: 'ml', risk_level: 'high', score: 0.62, calibrated_probability: 0.62, probability_valid: true, horizon_hours: 24, factors: [], data_quality: {}, uncertainty: {level: 'moderate'}, evidence: {}};
const anomaly = {id: 13, domain: 'cardiovascular', risk_type: 'anomaly_resting_heart_rate', title: 'Statistical anomaly in resting heart rate', prediction_kind: 'anomaly', risk_level: 'low', score: 4.1, score_meaning: 'Robust z-score. It is an anomaly score, not a disease probability.', calibrated_probability: null, probability_valid: false, horizon_hours: 24, factors: [], data_quality: {}, uncertainty: {level: 'moderate'}, evidence: {}};
const insufficient = {id: 14, domain: 'musculoskeletal', risk_type: 'musculoskeletal_insufficient_data', title: 'Musculoskeletal deconditioning', prediction_kind: 'insufficient_data', risk_level: 'undetermined', score: null, calibrated_probability: null, probability_valid: false, horizon_hours: null, factors: [], data_quality: {missing_sources: ['Bone mineral density measurements']}, uncertainty: {level: 'not_assessable'}, evidence: {}};
let recommendation = {id: 21, status: 'pending', urgency: 'within_72_hours', rank_score: 0.81, priority: 2, rationale: 'Suggested for a rule-based signal. This is a preventive suggestion for human review, not a diagnosis or prescription.', can_decide: true, feedback: [], outcomes: [],
  action: {name: 'Review rest periods and sleep schedule', description: 'Review scheduled sleep opportunities.', action_category: 'operational', responsible_roles: ['mission_admin', 'flight_surgeon'], version: 1, source_references: [{title: 'NASA OCHMO-TB-041 Sleep Accommodations'}]},
  explanation: {state: 'pending'}, sources: []};
const astronautView = () => ({astronaut_id: 2, mission_id: 1, visible_domains: ['cardiovascular', 'musculoskeletal', 'sleep'], notice: 'Predictive results are preventive attention indicators for human review.',
  latest: {id: 5, as_of: '2026-11-14T12:00:00Z', trigger: 'scheduled', engine_version: 'predictive-engine-v1', model_versions: {rules: 'predictive-rules-v1', models: ['astronaut_elevated_fatigue_24h:v1']}, predictions: [insufficient, anomaly, rulePrediction, mlPrediction]},
  indicators: {sleep_duration: {unit: 'min', latest_value: 315, mean_7d: 320, baseline_mean: 450, baseline_source: 'individual_history', z_7d: -3.4, slope_per_day: -12, n_7d: 4}},
  data_quality: {sleep_duration: 'sufficient'}, timeline: {sleep_duration: [{at: '2026-11-10T07:00:00Z', value: 330}, {at: '2026-11-11T07:00:00Z', value: 320}, {at: '2026-11-12T07:00:00Z', value: 315}]},
  history: [{id: 5, as_of: '2026-11-14T12:00:00Z', trigger: 'scheduled', status: 'completed', signals: 3, kinds: {rule: 1, ml: 1, anomaly: 1, insufficient_data: 1}}], recommendations: [recommendation]});

const browser = await chromium.launch({headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || '/usr/bin/google-chrome'});
try {
  const page = await browser.newPage();
  const mutations = [];
  await page.route('http://predictive.test/**', async route => {
    const url = new URL(route.request().url()), method = route.request().method();
    if (url.pathname === '/v1/predictions/dashboard') return route.fulfill({json: {monitored_astronauts: 1, visible_astronauts: 1, monitored_missions: 1, missions: [{mission_id: 1, name: 'Synthetic predictive mission', status: 'in_progress', analyzed_at: '2026-11-14T12:00:00Z', signals: 1, highest_level: 'moderate', risk_types: ['food_expiration']}],
      astronauts: [{astronaut_id: 2, name: 'Astro One', mission_id: 1, mission_name: 'Synthetic predictive mission', analyzed_at: '2026-11-14T12:00:00Z', signals: 3, insufficient: 1, risk_types: ['sleep_fatigue_combined']}],
      risk_levels: {moderate: 2, high: 1}, prediction_kinds: {rule: 2, ml: 1}, domains: {sleep: 2, supplies: 1}, pending_recommendations: 1, top_recommendations: [], run_history: [{date: '2026-11-14', runs: 3}], failed_runs: 0, notice: 'Preventive indicators only.'}});
    if (url.pathname === '/v1/predictions/astronauts/2') return route.fulfill({json: astronautView()});
    if (url.pathname === '/v1/predictions/astronauts/2/analyze') {mutations.push({analyze: url.search});return route.fulfill({json: astronautView()});}
    if (url.pathname === '/v1/recommendations/21/evidence') {recommendation = {...recommendation, explanation: {state: 'documented', summary: 'Sleep accommodation guidance supports reviewing rest periods.', generated: true}, sources: [{id: 7, title: 'NASA OCHMO-TB-041 Sleep Accommodations', page: 2, revision: 'Rev B', source_url: 'https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-041-sleep-accommodations.pdf', excerpt: 'Sleep accommodations protect the sleep opportunity.'}]};return route.fulfill({json: recommendation});}
    if (url.pathname === '/v1/recommendations/21/feedback') {const body = route.request().postDataJSON();mutations.push(body);recommendation = {...recommendation, status: body.decision, feedback: [...recommendation.feedback, {id: recommendation.feedback.length + 1, decision: body.decision, justification: body.justification, executed_action: body.executed_action, created_at: '2026-11-14T13:00:00Z'}]};return route.fulfill({json: recommendation});}
    if (url.pathname === '/v1/prediction-models') return route.fulfill({json: []});
    return route.fulfill({status: 404, json: {detail: `Unexpected ${method} ${url.pathname}`}});
  });
  await page.setContent(`<!doctype html><html><body><div id="root"></div><script>${bundle}</script></body></html>`);
  await page.getByRole('heading', {name: 'Predictive Intelligence'}).waitFor();
  await page.getByText('Monitored astronauts').waitFor();
  await page.getByRole('button', {name: 'Open'}).first().click();
  await page.getByRole('heading', {name: 'Reduced sleep with increasing fatigue'}).waitFor();
  assert.equal(await page.locator('.predictive-kind.rule').count(), 1);
  assert.equal(await page.locator('.predictive-kind.ml').count(), 1);
  assert.equal(await page.locator('.predictive-kind.anomaly').count(), 1);
  assert.equal(await page.locator('.predictive-kind.insufficient_data').count(), 1);
  assert.equal(await page.getByText('62.0% calibrated probability').count(), 1);
  assert.equal(await page.getByText(/%/).filter({hasText: 'Reduced sleep'}).count(), 0);
  await page.getByText('Score 4.1 (not a probability)').waitFor();
  await page.getByText('Missing: Bone mineral density measurements').waitFor();
  await page.getByText('Excluded actions (1)').waitFor();
  await page.getByLabel('Sleep duration over 30 days').waitFor();
  await page.getByRole('button', {name: 'Retrieve evidence'}).click();
  await page.getByText('Documented with NASA references').click();
  await page.getByText('Sleep accommodations protect the sleep opportunity.').waitFor();
  await page.getByLabel('Justification').fill('Rest schedule can be reviewed today');
  await page.getByRole('button', {name: 'Save decision'}).click();
  await page.locator('.predictive-status.accepted').waitFor();
  await page.getByLabel('Decision').selectOption('executed');
  await page.getByLabel('Justification').fill('Schedule adjusted');
  await page.getByLabel('Action executed').fill('Two additional rest periods scheduled');
  await page.getByRole('button', {name: 'Save decision'}).click();
  await page.locator('.predictive-status.executed').waitFor();
  await page.getByText('Record observed result').waitFor();
  await page.getByRole('button', {name: 'Run analysis'}).click();
  assert.deepEqual(mutations, [{decision: 'accepted', justification: 'Rest schedule can be reviewed today', executed_action: null}, {decision: 'executed', justification: 'Schedule adjusted', executed_action: 'Two additional rest periods scheduled'}, {analyze: '?mission_id=1'}]);
  await page.getByRole('tab', {name: 'Models'}).click();
  await page.getByText('No trained model is registered').waitFor();
  console.log('Predictive Intelligence browser flow verified');
} finally {
  await browser.close();
}
