import test from 'node:test';
import assert from 'node:assert/strict';
import { displayValue, resultPayload } from '../src/exam-fields.js';

const fields = [
  { code: 'hemoglobin', type: 'number', unit: 'g/dL' },
  { code: 'fasting', type: 'boolean' },
  { code: 'notes', type: 'textarea' },
  { code: 'finding', type: 'select', options: [{ value: 'absent', label: 'Ausente' }] },
];

test('result payload preserves zero and false, references and collection metadata', () => {
  const data = new FormData();
  Object.entries({ 'value:hemoglobin': '0', 'value:fasting': 'false', 'value:notes': 'Observation', 'value:finding': 'absent', 'reference:hemoglobin': '  As per report  ', performed_at: '2026-01-01T10:00', collected_at: '2026-01-01T09:00', summary: '  Summary  ', laboratory: 'Lab', performer_name: "Physician", sample_identifier: 'sample', method: 'method', report_reference: 'report' }).forEach(([key, value]) => data.set(key, value));
  const body = resultPayload(data, fields);
  assert.deepEqual(body.structured_values, { hemoglobin: 0, fasting: false, notes: 'Observation', finding: 'absent' });
  assert.deepEqual(body.reference_ranges, { hemoglobin: 'As per report' });
  assert.equal(body.summary, 'Summary');
  assert.equal(body.laboratory, 'Lab');
  assert.equal(body.performed_at, new Date('2026-01-01T10:00').toISOString());
  assert.equal(body.collected_at, new Date('2026-01-01T09:00').toISOString());
});

test('blank optional fields stay absent and legacy results retain the summary', () => {
  const data = new FormData(); data.set('summary', 'Previous result'); data.set('performed_at', '2026-01-01T10:00'); data.set('value:hemoglobin', ''); data.set('value:fasting', '');
  const body = resultPayload(data, fields);
  assert.deepEqual(body.structured_values, {});
  assert.deepEqual(body.reference_ranges, {});
  assert.equal(body.collected_at, null);
  assert.equal(body.summary, 'Previous result');
  assert.deepEqual(resultPayload(data, []).structured_values, {});
});

test('result display distinguishes missing values, zero, false and selection labels', () => {
  assert.equal(displayValue(fields[0], 0), '0 g/dL');
  assert.equal(displayValue(fields[0], undefined), "Not provided");
  assert.equal(displayValue(fields[1], false), "No");
  assert.equal(displayValue(fields[1], true), "Yes");
  assert.equal(displayValue(fields[3], 'absent'), 'Ausente');
});
