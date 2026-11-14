import test from 'node:test';
import assert from 'node:assert/strict';
import { doseRows, eventSummary, fluxSeries, solarRadiationScale, sortRadiationAlerts, timelineRows, windowState } from '../src/radiation.js';

const flare = { id: 1, event_type: 'FLR', start_time: '2024-10-26T06:32:00Z', end_time: '2024-10-26T07:12:00Z', flare_class: 'X1.8', source_location: 'S16E62', active_region_num: 13869, health_relevance: 'precursor', instruments: [] };
const cme = { id: 2, event_type: 'CME', start_time: '2024-10-26T06:48:00Z', end_time: null, cme_speed_kms: 1100.4, cme_half_angle_deg: 45, cme_type: 'O', health_relevance: 'precursor', instruments: [] };
const sep = { id: 3, event_type: 'SEP', start_time: '2024-10-26T19:02:00Z', end_time: null, health_relevance: 'exposure', instruments: ['SOHO: COSTEP'] };

test('event summaries use the fields that matter for each event type', () => {
  assert.equal(eventSummary(flare), 'Class X1.8 · S16E62 · AR 13869');
  assert.equal(eventSummary(cme), '1100 km/s · half-angle 45° · type O');
  assert.equal(eventSummary(sep), 'SOHO: COSTEP');
  assert.equal(eventSummary({ event_type: 'FLR' }), 'Flare');
});

test('timeline merges events, EVAs and observation windows in chronological order', () => {
  const rows = timelineRows({
    events: [sep, cme, flare],
    activities: [
      { id: 7, activity_type: 'eva', started_at: '2024-10-26T17:00:00Z', ended_at: '2024-10-26T23:00:00Z' },
      { id: 8, activity_type: 'iva', started_at: '2024-10-26T00:00:00Z', ended_at: null },
    ],
    follow_ups: [{ id: 9, opened_at: '2024-10-26T19:02:00Z', window_ends_at: '2024-10-28T19:02:00Z', symptoms: ['nausea'] }],
  });
  assert.deepEqual(rows.map(row => row.key), ['event-1', 'event-2', 'activity-7', 'event-3', 'follow-up-9']);
  assert.equal(rows.at(-1).detail, 'Nausea');
  assert.deepEqual(timelineRows(null), []);
});

test('flux series keeps the highest reading per timestamp and the NOAA S-scale', () => {
  const series = fluxSeries([
    { observed_at: '2024-10-26T19:05:00Z', flux_pfu: 12, source: 'noaa_swpc' },
    { observed_at: '2024-10-26T19:05:00Z', flux_pfu: 15, source: 'simulation' },
    { observed_at: '2024-10-26T19:00:00Z', flux_pfu: 3, source: 'noaa_swpc' },
  ]);
  assert.deepEqual(series.map(point => [point.flux, point.simulated]), [[3, false], [15, true]]);
  assert.deepEqual([5, 10, 150, 1000, 2e6].map(solarRadiationScale), [null, 'S1', 'S2', 'S3', 'S5']);
});

test('alerts, dose rows and observation windows are ordered and labeled', () => {
  const alerts = sortRadiationAlerts([
    { severity: 'critical', status: 'resolved', updated_at: '2024-10-27T00:00:00Z' },
    { severity: 'attention', status: 'open', updated_at: '2024-10-27T00:00:00Z' },
    { severity: 'critical', status: 'acknowledged', updated_at: '2024-10-26T00:00:00Z' },
  ]);
  assert.deepEqual(alerts.map(alert => `${alert.severity}/${alert.status}`), ['critical/acknowledged', 'attention/open', 'critical/resolved']);
  const rows = doseRows({ items: [{ organ: 'bfo', period: '1_year' }, { organ: 'skin', period: 'career' }, { organ: 'bfo', period: '30_day' }] });
  assert.deepEqual(rows.map(row => `${row.organ}/${row.period}`), ['skin/career', 'bfo/30_day', 'bfo/1_year']);
  const open = { status: 'open', window_ends_at: '2024-10-28T19:02:00Z' };
  assert.equal(windowState(open, Date.parse('2024-10-28T17:00:00Z')), '2 h 02 min left');
  assert.equal(windowState(open, Date.parse('2024-10-29T00:00:00Z')), 'Window ended · awaiting closure');
  assert.equal(windowState({ ...open, status: 'completed' }), 'Completed');
});
