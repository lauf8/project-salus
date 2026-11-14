import React, { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { booleanValue, fieldErrors, modulePayload, spacecraftPayload, validatePayload } from './forms';
import type { ApiError, FieldErrors, Material, Request, Spacecraft, SpacecraftModule } from './types';

export function Dialog({ title, busy = false, onClose, children }: { title: string; busy?: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>('input,select,textarea,button');
    first?.focus();
    return () => previous?.focus();
  }, []);
  return <div className="overlay" onKeyDown={event => {
    if (event.key === 'Escape' && !busy) onClose();
    if (event.key === 'Tab') {
      const elements = [...(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href]') || [])];
      const first = elements[0], last = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }}><section ref={ref} className="modal spacecraft-modal" role="dialog" aria-modal="true" aria-label={title}><header><h2>{title}</h2><button className="icon" type="button" aria-label="Close" disabled={busy} onClick={onClose}>×</button></header>{children}</section></div>;
}

type Props = { request: Request; spacecraftId?: number; initial?: Spacecraft | SpacecraftModule; onClose: () => void; onSaved: (record: Spacecraft | SpacecraftModule) => void };

export default function SpacecraftForm({ request, spacecraftId, initial, onClose, onSaved }: Props) {
  const module = spacecraftId !== undefined;
  const initialModule = module ? initial as SpacecraftModule | undefined : undefined;
  const specification = initialModule?.technical_specifications;
  const [materials, setMaterials] = useState<Material[]>(() => (specification?.materials || []).map(item => ({ ...item })));
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [errors, setErrors] = useState<FieldErrors>({});
  const title = `${initial ? 'Edit' : 'Add'} ${module ? 'module' : 'spacecraft'}`;
  const message = (name: string) => errors[name] ? <small id={`error-${name}`} className="field-error">{errors[name]}</small> : null;
  const invalid = (name: string) => ({ 'aria-invalid': Boolean(errors[name]), 'aria-describedby': errors[name] ? `error-${name}` : undefined });
  const input = (name: string, label: string, value?: string | number | null, type = 'text', required = false) => <label>{label}<input name={name} aria-label={label} type={type} required={required} defaultValue={value ?? ''} {...(type === 'number' ? { step: ['manufactured_year', 'maximum_crew_capacity'].includes(name) ? '1' : 'any', min: ['manufactured_year', 'maximum_crew_capacity'].includes(name) ? '1' : '0.000000001', max: name === 'manufactured_year' ? '32767' : name === 'maximum_crew_capacity' ? '2147483647' : undefined } : {})} {...invalid(name)}/>{message(name)}</label>;
  return <Dialog title={title} busy={busy} onClose={onClose}><form noValidate onSubmit={async event => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = module ? modulePayload(data, materials, initialModule) : spacecraftPayload(data);
    const validation = validatePayload(payload);
    setErrors(validation); setError('');
    if (Object.keys(validation).length) { setError('Please check the highlighted fields.'); return; }
    setBusy(true);
    try {
      const path = module ? `/v1/spacecraft/${spacecraftId}/modules` : '/v1/spacecraft';
      const saved = await request<Spacecraft | SpacecraftModule>(`${path}${initial ? `/${initial.id}` : ''}`, { method: initial ? 'PATCH' : 'POST', body: payload });
      onSaved(saved);
    } catch (caught) {
      const failure = caught as ApiError;
      setError(failure.message); setErrors(fieldErrors(failure, module));
    } finally { setBusy(false); }
  }}><fieldset disabled={busy}><legend>Identification</legend><div className="spacecraft-form-grid">
    {input('name', 'Name', initial?.name, 'text', true)}
    {module ? input('code', 'Code', initialModule?.code, 'text', true) : input('model', 'Model / class', (initial as Spacecraft | undefined)?.model)}
    {!module && input('maximum_crew_capacity', 'Maximum crew capacity (people)', (initial as Spacecraft | undefined)?.maximum_crew_capacity, 'number')}
    {input('manufacturer', 'Manufacturer', initial?.manufacturer)}
    {input('serial_number', 'Serial number', initial?.serial_number)}
    {input('manufactured_year', 'Manufactured year', initial?.manufactured_year, 'number')}
    {input('technical_reference_url', 'Technical reference URL', initial?.technical_reference_url, 'url')}
  </div>
  {module ? <>
    <label>Purpose<textarea name="purpose" aria-label="Purpose" defaultValue={initialModule?.purpose ?? ''} rows={3}/></label>
    <div className="spacecraft-form-grid">{(['is_pressurized', 'is_habitable'] as const).map(key => <label key={key}>{key === 'is_pressurized' ? 'Pressurized' : 'Habitable'}<select name={key} aria-label={key === 'is_pressurized' ? 'Pressurized' : 'Habitable'} defaultValue={booleanValue(initialModule?.[key])}><option value="unknown">Unknown</option><option value="true">Yes</option><option value="false">No</option></select>{message(key)}</label>)}{input('pressurized_volume_m3', 'Pressurized volume (m³)', initialModule?.pressurized_volume_m3, 'number')}</div>
    <fieldset><legend>Dimensions (m)</legend><div className="spacecraft-form-grid">{(['length', 'width', 'height', 'diameter'] as const).map(key => <React.Fragment key={key}>{input(key, key[0].toUpperCase() + key.slice(1), specification?.dimensions_m?.[key], 'number')}</React.Fragment>)}</div></fieldset>
    <fieldset><legend>Mass</legend>{input('dry_mass_kg', 'Dry mass (kg)', specification?.dry_mass_kg, 'number')}</fieldset>
    <fieldset><legend>Materials by component</legend><p className="muted">Add the documented materials. Component and material are required for each row.</p>
      {materials.map((item, index) => <div className="spacecraft-material-row" key={index}><h3>Material {index + 1}</h3><div className="spacecraft-form-grid">{(['component', 'material', 'location', 'specification', 'contact_environment'] as const).map(key => {
        const label = { component: 'Component', material: 'Material', location: 'Location', specification: 'Specification', contact_environment: 'Contact environment' }[key];
        const errorKey = `materials.${index}.${key}`;
        return <label key={key}>{label}<input aria-label={`Material ${index + 1} ${label.toLowerCase()}`} required={key === 'component' || key === 'material'} value={item[key] ?? ''} {...invalid(errorKey)} onChange={event => setMaterials(rows => rows.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: event.target.value } : row))}/>{message(errorKey)}</label>;
      })}</div><button type="button" className="secondary danger" onClick={() => setMaterials(rows => rows.filter((_, rowIndex) => rowIndex !== index))}>Remove material {index + 1}</button></div>)}
      {!materials.length && <p className="muted">No materials added.</p>}<button type="button" className="secondary" onClick={() => setMaterials(rows => [...rows, { component: '', material: '' }])}>Add material</button>{message('materials')}
    </fieldset>
    <fieldset><legend>Insulation and shielding</legend><label>Thermal insulation<textarea name="thermal_insulation" aria-label="Thermal insulation" rows={3} defaultValue={specification?.thermal_insulation ?? ''}/>{message('thermal_insulation')}</label><label>Shielding<textarea name="shielding" aria-label="Shielding" rows={3} defaultValue={specification?.shielding ?? ''}/>{message('shielding')}</label></fieldset>
  </> : <label>Description<textarea name="description" aria-label="Description" rows={4} defaultValue={(initial as Spacecraft | undefined)?.description ?? ''}/></label>}
  </fieldset>{error && <div className="error" role="alert">{error}</div>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button disabled={busy}>{busy ? 'Saving…' : `Save ${module ? 'module' : 'spacecraft'}`}</button></footer></form></Dialog>;
}
