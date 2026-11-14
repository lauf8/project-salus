import test from 'node:test';
import assert from 'node:assert/strict';
import { measurementContext, measurementFields } from '../src/measurement-fields.js';
import { observationContext } from '../src/health-alerts.js';

function data(values) {
  return { get: key => values[key] ?? null, getAll: key => values[key] ?? [] };
}

test('glucose has meal and quality fields without respiratory or activity fields', () => {
  assert.deepEqual(measurementFields('blood_glucose'), { activity: false, oxygen: false, quality: true, meal: true, symptoms: false, confusion: false });
  const payload = measurementContext('blood_glucose', data({ glucose_context: 'fasting', signal_quality: 'good', supplemental_oxygen: 'true', activity: 'exercise' }));
  assert.deepEqual(payload, { signal_quality: 'good', glucose_context: 'fasting' });
  const description = observationContext({ indicator: 'blood_glucose', ...payload });
  assert.match(description, /Fasting/);
  assert.doesNotMatch(description, /oxygen|at rest|exercise/);
});

test('oxygen fields are limited to respiratory measurements', () => {
  for (const indicator of ['oxygen_saturation', 'respiratory_rate']) assert.equal(measurementFields(indicator).oxygen, true);
  for (const indicator of ['heart_rate', 'blood_pressure', 'body_temperature', 'mood', 'sleep_duration']) assert.equal(measurementFields(indicator).oxygen, false);
});

test('subjective and sleep measurements do not request sensor quality', () => {
  for (const indicator of ['sleep_duration', 'sleep_quality', 'mood', 'fatigue']) assert.deepEqual(measurementContext(indicator, data({ signal_quality: 'good' })), {});
  assert.deepEqual(measurementContext('attention', data({ acute_confusion: 'true', supplemental_oxygen: 'true' })), { acute_confusion: true });
});
