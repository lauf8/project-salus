export const activityLabels = { iva: 'IVA · inside the spacecraft', eva: 'EVA · spacewalk', storm_shelter: 'Storm shelter' };
export const radiationSymptomLabels = { nausea: 'Nausea', vomiting: 'Vomiting', anorexia: 'Loss of appetite', fatigue: 'Fatigue', skin_erythema: 'Skin redness or burning' };
export const organLabels = { skin: 'Skin', lens: 'Eye lens', bfo: 'Blood-forming organs', heart: 'Heart', cns: 'Central nervous system', cns_z_ge_10: 'CNS (ions Z ≥ 10)' };
export const periodLabels = { '30_day': '30 days', '1_year': '1 year', career: 'Career' };
export const doseSourceLabels = { dosimeter: 'Dosimeter', model_estimate: 'Model estimate', simulation: 'Simulation' };
export const followUpStatusLabels = { open: 'Open', completed: 'Completed', cancelled: 'Cancelled' };
export const radiationRuleLabels = {
  sep_during_eva: 'SEP during EVA',
  proton_flux_during_eva: 'Proton flux during EVA',
  prodromal_vomiting: 'Vomiting after SEP',
  prodromal_symptoms: 'Prodromal symptoms',
  skin_reaction: 'Skin reaction',
  late_symptoms: 'Symptoms after the 48 h window',
  dose_limit: 'Dose limit',
};
export const eventTypeLabels = { FLR: 'Solar flare', CME: 'Coronal mass ejection', SEP: 'Solar energetic particles' };
const severityRank = { attention: 1, urgent: 2, critical: 3 };

/** One-line description of a DONKI event, using the fields relevant to each type. */
export function eventSummary(event) {
  if (event.event_type === 'FLR') return [event.flare_class && `Class ${event.flare_class}`, event.source_location, event.active_region_num && `AR ${event.active_region_num}`].filter(Boolean).join(' · ') || 'Flare';
  if (event.event_type === 'CME') return [event.cme_speed_kms != null && `${Math.round(event.cme_speed_kms)} km/s`, event.cme_half_angle_deg != null && `half-angle ${event.cme_half_angle_deg}°`, event.cme_type && `type ${event.cme_type}`].filter(Boolean).join(' · ') || 'CME';
  return event.instruments?.length ? event.instruments.join(', ') : 'Proton event';
}

/** Chronological rows for the timeline: events, crew activities and 48 h windows. */
export function timelineRows(timeline) {
  if (!timeline) return [];
  const rows = [
    ...timeline.events.map(event => ({ key: `event-${event.id}`, kind: 'event', at: event.start_time, end: event.end_time, type: event.event_type, title: eventTypeLabels[event.event_type], detail: eventSummary(event), role: event.health_relevance, item: event })),
    ...timeline.activities.filter(activity => activity.activity_type !== 'iva').map(activity => ({ key: `activity-${activity.id}`, kind: 'activity', at: activity.started_at, end: activity.ended_at, type: activity.activity_type, title: activityLabels[activity.activity_type], detail: '', item: activity })),
    ...timeline.follow_ups.map(followUp => ({ key: `follow-up-${followUp.id}`, kind: 'follow_up', at: followUp.opened_at, end: followUp.window_ends_at, type: 'follow_up', title: '48 h observation window', detail: followUp.symptoms.length ? followUp.symptoms.map(key => radiationSymptomLabels[key] || key).join(', ') : 'No symptoms reported', item: followUp })),
  ];
  return rows.sort((a, b) => Date.parse(a.at) - Date.parse(b.at) || a.key.localeCompare(b.key));
}

/** Highest flux per timestamp across satellites/sources, ready for a chart. */
export function fluxSeries(readings) {
  const byTime = new Map();
  for (const reading of readings) {
    const time = Date.parse(reading.observed_at);
    const current = byTime.get(time);
    if (!current || reading.flux_pfu > current.flux) byTime.set(time, { time, flux: reading.flux_pfu, simulated: reading.source === 'simulation' });
  }
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

/** NOAA S-scale for the ≥10 MeV integral proton flux (pfu). */
export function solarRadiationScale(flux) {
  if (flux == null || flux < 10) return null;
  return `S${Math.min(5, Math.floor(Math.log10(flux)))}`;
}

export function sortRadiationAlerts(alerts) {
  return [...alerts].sort((a, b) => Number(a.status === 'resolved') - Number(b.status === 'resolved') || severityRank[b.severity] - severityRank[a.severity] || Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

export function doseRows(summary) {
  if (!summary) return [];
  const order = Object.keys(organLabels), periods = Object.keys(periodLabels);
  return [...summary.items].sort((a, b) => order.indexOf(a.organ) - order.indexOf(b.organ) || periods.indexOf(a.period) - periods.indexOf(b.period));
}

export function windowState(followUp, now = Date.now()) {
  if (followUp.status !== 'open') return followUpStatusLabels[followUp.status];
  const remaining = Date.parse(followUp.window_ends_at) - now;
  if (remaining <= 0) return 'Window ended · awaiting closure';
  const hours = Math.floor(remaining / 3600000), minutes = Math.floor(remaining % 3600000 / 60000);
  return `${hours} h ${String(minutes).padStart(2, '0')} min left`;
}

export function isoFromLocal(value) {
  return value ? new Date(value).toISOString() : null;
}
