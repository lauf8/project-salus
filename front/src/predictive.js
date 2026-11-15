export const kindLabels = {
  rule: 'Rule-based risk',
  anomaly: 'Statistical anomaly',
  ml: 'Machine learning prediction',
  insufficient_data: 'Insufficient information',
};

export const levelLabels = { high: 'High', moderate: 'Moderate', low: 'Low', none: 'None', undetermined: 'Undetermined' };
export const urgencyLabels = { within_24_hours: 'Within 24 hours', within_72_hours: 'Within 72 hours', routine: 'Routine' };
export const statusLabels = { pending: 'Pending', accepted: 'Accepted', rejected: 'Rejected', executed: 'Executed', superseded: 'Superseded' };
export const evidenceLabels = {
  pending: 'Evidence retrieval pending',
  documented: 'Documented with NASA references',
  no_documentary_evidence: 'No applicable documentary evidence found',
  rag_unavailable: 'Document retrieval unavailable',
};
export const domainLabels = {
  cardiovascular: 'Cardiovascular', sleep: 'Sleep and fatigue', psychological: 'Psychological attention', nutrition: 'Nutrition',
  musculoskeletal: 'Musculoskeletal', supplies: 'Supplies', crew_health: 'Collective crew health', operations: 'Operations',
  spacecraft: 'Spacecraft', other: 'Other',
};
export const indicatorLabels = {
  resting_heart_rate: 'Resting heart rate', systolic_pressure: 'Systolic pressure', diastolic_pressure: 'Diastolic pressure',
  respiratory_rate: 'Respiratory rate', oxygen_saturation: 'Oxygen saturation', body_temperature: 'Body temperature',
  blood_glucose: 'Blood glucose', sleep_duration: 'Sleep duration', sleep_quality: 'Sleep quality', fatigue: 'Fatigue', mood: 'Mood',
  mental_stress: 'Stress', mental_happiness: 'Happiness', mental_satisfaction: 'Satisfaction', mental_energy: 'Energy',
  mental_isolation: 'Isolation', mental_workload: 'Workload', mental_crew_connection: 'Crew connection',
  energy_intake: 'Energy intake', protein_intake: 'Protein intake',
};

const levelRank = { high: 3, moderate: 2, low: 1, none: 0, undetermined: -1 };
const kindRank = { ml: 0, rule: 1, anomaly: 2, insufficient_data: 3 };

export const label = value => String(value ?? '').replaceAll('_', ' ');
export const indicatorName = key => indicatorLabels[key] || label(key);

export function sortPredictions(predictions = []) {
  return [...predictions].sort((a, b) =>
    (kindRank[a.prediction_kind] === 3) - (kindRank[b.prediction_kind] === 3)
    || (levelRank[b.risk_level] ?? -1) - (levelRank[a.risk_level] ?? -1)
    || kindRank[a.prediction_kind] - kindRank[b.prediction_kind]
    || String(a.risk_type).localeCompare(String(b.risk_type)));
}

export function probabilityText(prediction) {
  if (!prediction || prediction.prediction_kind !== 'ml' || !prediction.probability_valid || prediction.calibrated_probability == null) return null;
  return `${(prediction.calibrated_probability * 100).toFixed(1)}% calibrated probability`;
}

export function scoreText(prediction) {
  if (!prediction || prediction.score == null) return 'Not assessable';
  if (prediction.prediction_kind === 'ml') return probabilityText(prediction) || 'Probability unavailable';
  return `Score ${Number(prediction.score).toLocaleString('en-US', { maximumFractionDigits: 3 })} (not a probability)`;
}

export function signalSummary(predictions = []) {
  const signals = predictions.filter(row => row.prediction_kind !== 'insufficient_data');
  return {
    signals: signals.length,
    insufficient: predictions.length - signals.length,
    highest: signals.reduce((best, row) => (levelRank[row.risk_level] ?? -1) > (levelRank[best] ?? -1) ? row.risk_level : best, null),
  };
}

export function indicatorRows(indicators = {}, quality = {}) {
  return Object.entries(indicators).map(([key, values]) => ({
    key, name: indicatorName(key), unit: values.unit || '', latest: values.latest_value, mean7d: values.mean_7d, baseline: values.baseline_mean,
    baselineSource: values.baseline_source, z: values.z_7d, slope: values.slope_per_day, points7d: values.n_7d, quality: quality[key] || 'missing',
  })).sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0) || a.name.localeCompare(b.name));
}

export function chartPoints(points = [], baseline = null) {
  return points.map(point => ({
    at: point.at,
    label: new Date(point.at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    value: point.value,
    baseline,
    preflight: Boolean(point.preflight_reference),
  }));
}

export function feedbackOptions(recommendation) {
  if (!recommendation?.can_decide) return [];
  return { pending: ['accepted', 'rejected'], accepted: ['executed', 'rejected'] }[recommendation.status] || [];
}

export function canRecordOutcome(recommendation) {
  return Boolean(recommendation?.can_decide && ['accepted', 'executed'].includes(recommendation.status));
}

export function supplyRows(context) {
  return (context?.supplies || []).map(row => ({
    ...row,
    margin: row.safety_margin_days == null ? 'Not computable' : `${row.safety_margin_days} days`,
    depletion: row.estimated_depletion_date || (row.state === 'sufficient' ? 'Not before mission end' : 'Not computable'),
  }));
}
