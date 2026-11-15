import test from 'node:test';
import assert from 'node:assert/strict';
import { canRecordOutcome, chartPoints, feedbackOptions, indicatorRows, probabilityText, scoreText, signalSummary, sortPredictions, supplyRows } from '../src/predictive.js';

const rule = { id: 1, risk_type: 'sleep_deficit', prediction_kind: 'rule', risk_level: 'low', score: 2.4, calibrated_probability: null, probability_valid: false };
const combined = { id: 2, risk_type: 'sleep_fatigue_combined', prediction_kind: 'rule', risk_level: 'moderate', score: 3.1, calibrated_probability: null, probability_valid: false };
const anomaly = { id: 3, risk_type: 'anomaly_resting_heart_rate', prediction_kind: 'anomaly', risk_level: 'moderate', score: 4.2, calibrated_probability: null };
const ml = { id: 4, risk_type: 'elevated_fatigue_24h', prediction_kind: 'ml', risk_level: 'high', score: 0.62, calibrated_probability: 0.623, probability_valid: true };
const missing = { id: 5, risk_type: 'musculoskeletal_insufficient_data', prediction_kind: 'insufficient_data', risk_level: 'undetermined', score: null };

test('predictions are ordered by level with insufficient information last', () => {
  assert.deepEqual(sortPredictions([missing, rule, anomaly, combined, ml]).map(row => row.id), [4, 2, 3, 1, 5]);
});

test('probabilities are shown only for validated machine learning predictions', () => {
  assert.equal(probabilityText(ml), '62.3% calibrated probability');
  assert.equal(probabilityText({ ...ml, probability_valid: false }), null);
  assert.equal(probabilityText(anomaly), null);
  assert.equal(probabilityText({ ...rule, calibrated_probability: 0.5 }), null);
  assert.equal(scoreText(anomaly), 'Score 4.2 (not a probability)');
  assert.equal(scoreText(missing), 'Not assessable');
});

test('signal summary separates insufficient information', () => {
  assert.deepEqual(signalSummary([rule, combined, missing]), { signals: 2, insufficient: 1, highest: 'moderate' });
  assert.deepEqual(signalSummary([missing]), { signals: 0, insufficient: 1, highest: null });
});

test('indicator rows rank by deviation and keep missing quality explicit', () => {
  const rows = indicatorRows({ sleep_duration: { z_7d: -3.2, mean_7d: 320, baseline_mean: 450, unit: 'min' }, fatigue: { z_7d: 2.1 }, mood: {} }, { sleep_duration: 'sufficient' });
  assert.deepEqual(rows.map(row => row.key), ['sleep_duration', 'fatigue', 'mood']);
  assert.equal(rows[0].name, 'Sleep duration');
  assert.equal(rows[2].quality, 'missing');
});

test('chart points carry the individual baseline', () => {
  const points = chartPoints([{ at: '2026-11-01T07:00:00Z', value: 430, preflight_reference: false }], 450);
  assert.equal(points[0].baseline, 450);
  assert.equal(points[0].value, 430);
});

test('feedback options follow the recommendation lifecycle and permissions', () => {
  assert.deepEqual(feedbackOptions({ can_decide: true, status: 'pending' }), ['accepted', 'rejected']);
  assert.deepEqual(feedbackOptions({ can_decide: true, status: 'accepted' }), ['executed', 'rejected']);
  assert.deepEqual(feedbackOptions({ can_decide: true, status: 'executed' }), []);
  assert.deepEqual(feedbackOptions({ can_decide: false, status: 'pending' }), []);
  assert.equal(canRecordOutcome({ can_decide: true, status: 'executed' }), true);
  assert.equal(canRecordOutcome({ can_decide: true, status: 'pending' }), false);
});

test('supply rows never invent a depletion date', () => {
  const [sufficient, unknown] = supplyRows({ supplies: [{ food_product_id: 1, state: 'sufficient', safety_margin_days: 4 }, { food_product_id: 2, state: 'inconclusive' }] });
  assert.equal(sufficient.depletion, 'Not before mission end');
  assert.equal(sufficient.margin, '4 days');
  assert.equal(unknown.depletion, 'Not computable');
  assert.equal(unknown.margin, 'Not computable');
});
