export const fieldTypes = { number: "Number", text: "Short text", textarea: "Long text", select: "Selection", boolean: "Yes or no", date: "Date" };

export function resultPayload(data, fields) {
  const structured_values = {}, reference_ranges = {};
  for (const field of fields) {
    const value = data.get(`value:${field.code}`);
    if (value !== null && value !== '') structured_values[field.code] = field.type === 'number' ? Number(value) : field.type === 'boolean' ? value === 'true' : value;
    const reference = data.get(`reference:${field.code}`)?.trim();
    if (reference) reference_ranges[field.code] = reference;
  }
  const body = { structured_values, reference_ranges };
  for (const key of ['performed_at', 'collected_at', 'summary', 'laboratory', 'performer_name', 'sample_identifier', 'method', 'report_reference']) {
    const value = data.get(key)?.trim();
    body[key] = key.endsWith('_at') ? (value ? new Date(value).toISOString() : null) : value || null;
  }
  return body;
}

export function displayValue(field, value) {
  if (value === undefined || value === null || value === '') return "Not provided";
  if (field.type === 'boolean') return value ? "Yes" : "No";
  if (field.type === 'select') return field.options.find(option => option.value === value)?.label || value;
  return `${value}${field.unit ? ` ${field.unit}` : ''}`;
}
