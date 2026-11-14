import type { ApiError, FieldErrors, Material, ModulePayload, SpacecraftModule, SpacecraftPayload, TechnicalSpecifications } from './types';

const text = (value: FormDataEntryValue | null): string | null => String(value ?? '').trim() || null;
const numeric = (value: FormDataEntryValue | null): number | null => text(value) === null ? null : Number(value);
export const booleanLabel = (value: boolean | null | undefined): string => value === true ? 'Yes' : value === false ? 'No' : 'Unknown';
export const booleanValue = (value: boolean | null | undefined): string => value === true ? 'true' : value === false ? 'false' : 'unknown';
const boolean = (value: FormDataEntryValue | null): boolean | null => value === 'true' ? true : value === 'false' ? false : null;

export function spacecraftPayload(data: FormData): SpacecraftPayload {
  return { name: text(data.get('name')) || '', maximum_crew_capacity: numeric(data.get('maximum_crew_capacity')), model: text(data.get('model')), manufacturer: text(data.get('manufacturer')), serial_number: text(data.get('serial_number')), manufactured_year: numeric(data.get('manufactured_year')), description: text(data.get('description')), technical_reference_url: text(data.get('technical_reference_url')) };
}

export function normalizeSpecifications(value: TechnicalSpecifications | null | undefined): TechnicalSpecifications {
  return {
    dimensions_m: { length: value?.dimensions_m?.length ?? null, width: value?.dimensions_m?.width ?? null, height: value?.dimensions_m?.height ?? null, diameter: value?.dimensions_m?.diameter ?? null },
    dry_mass_kg: value?.dry_mass_kg ?? null,
    materials: (value?.materials || []).map(item => ({ component: item.component.trim(), material: item.material.trim(), location: item.location?.trim() || null, specification: item.specification?.trim() || null, contact_environment: item.contact_environment?.trim() || null })),
    thermal_insulation: value?.thermal_insulation?.trim() || null,
    shielding: value?.shielding?.trim() || null,
  };
}

export function modulePayload(data: FormData, materials: Material[], initial?: SpacecraftModule): ModulePayload {
  const specification = normalizeSpecifications({
    dimensions_m: { length: numeric(data.get('length')), width: numeric(data.get('width')), height: numeric(data.get('height')), diameter: numeric(data.get('diameter')) },
    dry_mass_kg: numeric(data.get('dry_mass_kg')), materials,
    thermal_insulation: text(data.get('thermal_insulation')), shielding: text(data.get('shielding')),
  });
  const payload: ModulePayload = {
    name: text(data.get('name')) || '', code: text(data.get('code')) || '', purpose: text(data.get('purpose')),
    manufacturer: text(data.get('manufacturer')), serial_number: text(data.get('serial_number')), manufactured_year: numeric(data.get('manufactured_year')),
    is_pressurized: boolean(data.get('is_pressurized')), is_habitable: boolean(data.get('is_habitable')),
    pressurized_volume_m3: numeric(data.get('pressurized_volume_m3')), technical_reference_url: text(data.get('technical_reference_url')),
  };
  if (!initial || JSON.stringify(specification) !== JSON.stringify(normalizeSpecifications(initial.technical_specifications))) {
    const populated = Object.values(specification.dimensions_m || {}).some(value => value !== null) || specification.dry_mass_kg !== null || specification.materials?.length || specification.thermal_insulation || specification.shielding;
    payload.technical_specifications = populated ? specification : null;
  }
  return payload;
}

export function validatePayload(payload: SpacecraftPayload | ModulePayload): FieldErrors {
  const errors: FieldErrors = {};
  if (!payload.name) errors.name = 'Enter a name.';
  if ('code' in payload && !payload.code) errors.code = 'Enter a module code.';
  if (payload.manufactured_year !== null && (!Number.isInteger(payload.manufactured_year) || payload.manufactured_year < 1 || payload.manufactured_year > 32767)) errors.manufactured_year = 'Enter a whole year between 1 and 32767.';
  if ('maximum_crew_capacity' in payload && payload.maximum_crew_capacity !== null && (!Number.isInteger(payload.maximum_crew_capacity) || payload.maximum_crew_capacity < 1 || payload.maximum_crew_capacity > 2147483647)) errors.maximum_crew_capacity = 'Enter a whole number of people between 1 and 2147483647.';
  if (payload.technical_reference_url) {
    try { if (!['http:', 'https:'].includes(new URL(payload.technical_reference_url).protocol)) throw Error(); }
    catch { errors.technical_reference_url = 'Enter an HTTP or HTTPS URL.'; }
  }
  if ('pressurized_volume_m3' in payload && payload.pressurized_volume_m3 !== null && (!Number.isFinite(payload.pressurized_volume_m3) || payload.pressurized_volume_m3 <= 0)) errors.pressurized_volume_m3 = 'Enter a value greater than zero.';
  if ('technical_specifications' in payload) {
    const specification = payload.technical_specifications;
    for (const [key, value] of Object.entries(specification?.dimensions_m || {})) if (value !== null && value !== undefined && (!Number.isFinite(value) || value <= 0)) errors[key] = 'Enter a value greater than zero.';
    if (specification?.dry_mass_kg != null && (!Number.isFinite(specification.dry_mass_kg) || specification.dry_mass_kg <= 0)) errors.dry_mass_kg = 'Enter a value greater than zero.';
    specification?.materials?.forEach((item, index) => {
      for (const field of ['component', 'material'] as const) if (!item[field]) errors[`materials.${index}.${field}`] = 'This field is required.';
    });
  }
  return errors;
}

export function fieldErrors(error: ApiError, module: boolean): FieldErrors {
  if (error.status === 409 && module) return { code: error.message };
  if (!Array.isArray(error.detail)) return {};
  return Object.fromEntries(error.detail.map(item => [(item.loc || []).filter(key => !['body', 'technical_specifications', 'dimensions_m'].includes(String(key))).join('.'), item.msg]));
}
