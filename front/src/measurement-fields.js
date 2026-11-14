export function measurementFields(indicator) {
  return {
    activity: ['heart_rate', 'respiratory_rate', 'blood_pressure'].includes(indicator),
    oxygen: ['oxygen_saturation', 'respiratory_rate'].includes(indicator),
    quality: ['heart_rate', 'respiratory_rate', 'oxygen_saturation', 'body_temperature', 'blood_pressure', 'blood_glucose'].includes(indicator),
    meal: indicator === 'blood_glucose',
    symptoms: indicator === 'blood_pressure',
    confusion: ['attention', 'consciousness'].includes(indicator),
  };
}

export function measurementContext(indicator, data) {
  const fields = measurementFields(indicator);
  const context = {};
  if (fields.activity) context.activity = data.get('activity') || 'unknown';
  if (fields.oxygen) context.supplemental_oxygen = data.get('supplemental_oxygen') === 'true' ? true : data.get('supplemental_oxygen') === 'false' ? false : null;
  if (fields.quality) context.signal_quality = data.get('signal_quality') || 'unknown';
  if (fields.meal) context.glucose_context = data.get('glucose_context') || 'unknown';
  if (fields.symptoms) {
    context.symptoms_status = data.get('symptoms_status') || 'unknown';
    context.symptoms = data.getAll('symptoms');
  }
  if (fields.confusion) context.acute_confusion = data.get('acute_confusion') === 'true' ? true : data.get('acute_confusion') === 'false' ? false : null;
  return context;
}
