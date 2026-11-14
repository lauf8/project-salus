import test from 'node:test';
import assert from 'node:assert/strict';
import { alertStatusLabels, highestAlert, measurementStatusLabels, observationContext, sortAlerts, verificationMessage } from '../src/health-alerts.js';

const row = (severity, status = 'open', indicator = 'oxygen_saturation') => ({ severity, status, indicator, updated_at: '2026-11-01T10:00:00Z' });

test('active critical alerts precede urgent and attention alerts and resolved history', () => {
  const alerts = [row('critical', 'resolved'), row('attention'), row('urgent'), row('critical', 'acknowledged')];
  assert.deepEqual(sortAlerts(alerts).map(item => `${item.severity}/${item.status}`), ['critical/acknowledged', 'urgent/open', 'attention/open', 'critical/resolved']);
  assert.equal(highestAlert(alerts, 'oxygen_saturation').status, 'acknowledged');
  assert.equal(highestAlert(alerts, 'heart_rate'), undefined);
  assert.notEqual(alertStatusLabels.acknowledged, alertStatusLabels.resolved);
});

test('measurement states distinguish missing, stale, poor quality and evaluated readings', () => {
  assert.equal(new Set(['no_measurement', 'stale', 'insufficient_quality', 'evaluated'].map(status => measurementStatusLabels[status])).size, 4);
});

test('context preserves exercise, supplemental oxygen, poor quality and unknown symptoms', () => {
  const context = observationContext({ indicator: 'respiratory_rate', activity: 'exercise', supplemental_oxygen: true, signal_quality: 'poor' });
  assert.match(context, /exercise/);
  assert.match(context, /With supplemental oxygen/);
  assert.match(context, /Insufficient/);
  assert.match(observationContext({ indicator: 'blood_pressure', symptoms_status: 'unknown' }), /Unknown symptoms/);
  assert.doesNotMatch(context, /absent/);
  assert.match(observationContext({ indicator: 'attention', acute_confusion: true }), /New-onset confusion/);
  assert.match(observationContext({ indicator: 'blood_glucose', glucose_context: 'fasting' }), /Fasting/);
});

test('verification instructions match the alert instead of asking for unrelated symptoms', () => {
  const glucose = { rule_id: 'low_blood_glucose', verification_required: true, status: 'open', trigger_observation: { signal_quality: 'good' } };
  assert.doesNotMatch(verificationMessage(glucose), /symptoms/);
  assert.match(verificationMessage({ ...glucose, rule_id: 'very_high_blood_pressure' }), /symptoms/);
  assert.match(verificationMessage({ ...glucose, rule_id: 'resting_heart_rate_verification' }), /at rest/);
  assert.match(verificationMessage({ ...glucose, trigger_observation: { signal_quality: 'poor' } }), /immediately/);
  assert.equal(verificationMessage({ ...glucose, status: 'resolved' }), '');
  assert.equal(verificationMessage({ ...glucose, verification_required: false }), '');
});
