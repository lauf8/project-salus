import { measurementFields } from './measurement-fields.js';
import { radiationSymptomLabels } from './radiation.js';
export const severityRank = { attention: 1, urgent: 2, critical: 3 };
export const severityLabels = { attention: "Caution", urgent: "Urgent", critical: "Critical" };
export const alertStatusLabels = { open: "Active", acknowledged: "Acknowledged · still active", resolved: "Resolved" };
export const measurementStatusLabels = { no_measurement: "No measurement", stale: "Outdated measurement", insufficient_quality: "Insufficient quality", evaluated: "Measurement assessed", not_evaluated: "Recorded before automatic assessment" };
export const symptomLabels = { chest_pain: "Chest pain", shortness_of_breath: "Shortness of breath", sudden_weakness: "Sudden weakness", visual_changes: "Visual changes", speech_difficulty: "Difficulty speaking" };
export function highestAlert(alerts, indicator) {
  return alerts.filter(alert => alert.indicator === indicator && alert.status !== 'resolved').sort((a, b) => severityRank[b.severity] - severityRank[a.severity])[0];
}
export function sortAlerts(alerts) {
  return [...alerts].sort((a, b) => Number(a.status === 'resolved') - Number(b.status === 'resolved') || severityRank[b.severity] - severityRank[a.severity] || Date.parse(b.updated_at) - Date.parse(a.updated_at));
}
export function observationContext(row) {
  const values = [];
  const fields = measurementFields(row.indicator);
  if (fields.activity) values.push({ rest: "At rest", exercise: "During exercise", unknown: "Unknown activity" }[row.activity || 'unknown']);
  if (fields.oxygen) values.push(row.supplemental_oxygen === true ? "With supplemental oxygen" : row.supplemental_oxygen === false ? "Without supplemental oxygen" : "Oxygen use unknown");
  if (fields.quality) values.push({ good: "Good quality", poor: "Insufficient quality", unknown: "Quality not provided" }[row.signal_quality || 'unknown']);
  if (row.indicator === 'blood_glucose') values.push({ fasting: "Fasting", after_meal: "After a meal", unknown: "Unknown meal context" }[row.glucose_context || 'unknown']);
  if (row.indicator === 'blood_pressure') values.push(row.symptoms_status === 'present' ? `Symptoms: ${(row.symptoms || []).map(key => symptomLabels[key]).join(', ')}` : row.symptoms_status === 'absent' ? "Warning symptoms reported as absent" : "Unknown symptoms");
  if (row.acute_confusion === true) values.push("New-onset confusion");
  const radiation = (row.symptoms || []).filter(key => radiationSymptomLabels[key]);
  if (radiation.length) values.push(`Radiation symptoms: ${radiation.map(key => radiationSymptomLabels[key]).join(', ')}`);
  return values.filter(Boolean).join(' · ');
}

export function verificationMessage(alert) {
  if (!alert.verification_required || alert.status === 'resolved') return '';
  if (alert.awaiting_medical_review) return "The current reading has been recorded. The previous critical event is awaiting resolution by the flight surgeon.";
  if (alert.trigger_observation?.signal_quality === 'poor') return "Insufficient signal. Check the measurement immediately.";
  if (alert.rule_id.endsWith('_verification')) return "Confirm the reading and whether it was taken at rest.";
  if (alert.rule_id === 'very_high_blood_pressure') return "Record the associated symptoms and a new blood pressure measurement.";
  return "Confirm the reading without delaying the actions indicated for this alert.";
}
