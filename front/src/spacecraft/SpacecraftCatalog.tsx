import React, { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import SpacecraftForm, { Dialog } from './SpacecraftForm';
import { booleanLabel } from './forms';
import type { ApiError, Page, Request, Spacecraft, SpacecraftModule } from './types';
import './spacecraft.css';

const shown = (value: string | number | null | undefined): string | number => value ?? 'Not provided';
const craftLink = (id?: number): string => id ? `#spacecraft/${id}` : '#spacecraft';
const moduleLink = (craft: number, module: number): string => `#spacecraft/${craft}/modules/${module}`;

function useRecord<T>(request: Request, path: string | null, revision: number) {
  const [record, setRecord] = useState<T | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(Boolean(path));
  useEffect(() => {
    const controller = new AbortController();
    setRecord(null); setError(''); setLoading(Boolean(path));
    if (!path) return () => controller.abort();
    request<T>(path, { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setRecord(value); }).catch((failure: ApiError) => { if (!controller.signal.aborted) setError(failure.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, path, revision]);
  return { record, error, loading };
}

function LoadingError({ loading, error, retry }: { loading: boolean; error: string; retry: () => void }) {
  return <>{loading && <p role="status">Loading…</p>}{error && <div className="error" role="alert">{error}<button className="link" onClick={retry}>Try again</button></div>}</>;
}

function Collection<T extends { id: number; name: string }>({ request, path, revision, module = false, canManage, onEdit, onTotal }: { request: Request; path: string; revision: number; module?: boolean; canManage: boolean; onEdit: (item: T) => void; onTotal?: (count: number) => void }) {
  const [search, setSearch] = useState(''), [page, setPage] = useState(1), [reload, setReload] = useState(0);
  const { record: result, error, loading } = useRecord<Page<T>>(request, `${path}?${new URLSearchParams({ search, page: String(page), per_page: '10' })}`, revision + reload);
  useEffect(() => {
    if (!result) return;
    onTotal?.(result.pagination.total);
    if (!result.data.length && page > Math.max(1, result.pagination.total_pages)) setPage(Math.max(1, result.pagination.total_pages));
  }, [result, onTotal, page]);
  return <><div className="toolbar"><label>{module ? 'Search modules by name or code' : 'Search spacecraft by name, model or manufacturer'}<input type="search" value={search} onChange={event => { setSearch(event.target.value); setPage(1); }}/></label><button className="secondary" disabled={loading} onClick={() => setReload(value => value + 1)}>Refresh</button></div>
    <LoadingError loading={loading} error={error} retry={() => setReload(value => value + 1)}/>
    {result && !error && <><div className="panel table-wrap"><table><thead><tr><th>NAME</th>{module ? <><th>CODE</th><th>PURPOSE</th><th>PRESSURIZED</th><th>HABITABLE</th></> : <><th>MODEL</th><th>MANUFACTURER</th><th>YEAR</th><th>MAX. CREW</th><th>STATUS</th></>}<th>ACTIONS</th></tr></thead><tbody>{result.data.map(item => {
      const row = item as unknown as Spacecraft & SpacecraftModule;
      return <tr key={row.id}><td><strong>{row.name}</strong></td>{module ? <><td><code>{row.code}</code></td><td>{shown(row.purpose)}</td><td>{booleanLabel(row.is_pressurized)}</td><td>{booleanLabel(row.is_habitable)}</td></> : <><td>{shown(row.model)}</td><td>{shown(row.manufacturer)}</td><td>{shown(row.manufactured_year)}</td><td>{shown(row.maximum_crew_capacity)}</td><td>{row.status === 'in_use' ? 'In use' : 'Available'}</td></>}<td><div className="actions"><a className="link" href={module ? moduleLink(row.spacecraft_id, row.id) : craftLink(row.id)}>Open</a>{canManage && <button className="secondary" onClick={() => onEdit(item)}>Edit <span className="sr-only">{row.name}</span></button>}</div></td></tr>;
    })}</tbody></table>{!result.data.length && <p className="empty">{module ? 'No modules found.' : 'No spacecraft found.'}</p>}</div><div className="pagination"><span>Page {page} of {Math.max(1, result.pagination.total_pages)} · {result.pagination.total} records</span><button className="secondary" disabled={loading || !result.pagination.has_previous} onClick={() => setPage(value => value - 1)}>Previous</button><button className="secondary" disabled={loading || !result.pagination.has_next} onClick={() => setPage(value => value + 1)}>Next</button></div></>}
  </>;
}

function Details({ children }: { children: ReactNode }) {
  return <dl className="spacecraft-details">{children}</dl>;
}
function Detail({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <div><dt>{label}</dt><dd>{shown(value)}</dd></div>;
}
function Reference({ url }: { url: string | null }) {
  return <div className="spacecraft-reference"><h3>Technical reference</h3>{url && /^https?:\/\//i.test(url) ? <a href={url} target="_blank" rel="noreferrer">{url}</a> : <p>Not provided</p>}</div>;
}
function ModuleDetails({ module }: { module: SpacecraftModule }) {
  const specification = module.technical_specifications;
  return <><section className="panel spacecraft-section"><h2>Identification and purpose</h2><Details><Detail label="Code" value={module.code}/><Detail label="Purpose" value={module.purpose}/><Detail label="Manufacturer" value={module.manufacturer}/><Detail label="Serial number" value={module.serial_number}/><Detail label="Manufactured year" value={module.manufactured_year}/><Detail label="Pressurized" value={booleanLabel(module.is_pressurized)}/><Detail label="Habitable" value={booleanLabel(module.is_habitable)}/><Detail label="Pressurized volume (m³)" value={module.pressurized_volume_m3}/></Details><Reference url={module.technical_reference_url}/></section>
    <section className="panel spacecraft-section"><h2>Dimensions and mass</h2><Details>{(['length', 'width', 'height', 'diameter'] as const).map(key => <Detail key={key} label={`${key[0].toUpperCase() + key.slice(1)} (m)`} value={specification?.dimensions_m?.[key]}/>)}<Detail label="Dry mass (kg)" value={specification?.dry_mass_kg}/></Details></section>
    <section className="panel spacecraft-section"><h2>Materials by component</h2><div className="table-wrap"><table><thead><tr><th>COMPONENT</th><th>MATERIAL</th><th>LOCATION</th><th>SPECIFICATION</th><th>CONTACT ENVIRONMENT</th></tr></thead><tbody>{specification?.materials?.map((item, index) => <tr key={index}><td>{item.component}</td><td>{item.material}</td><td>{shown(item.location)}</td><td>{shown(item.specification)}</td><td>{shown(item.contact_environment)}</td></tr>)}</tbody></table></div>{!specification?.materials?.length && <p>No materials documented.</p>}</section>
    <section className="panel spacecraft-section"><h2>Thermal insulation</h2><p className="spacecraft-prose">{shown(specification?.thermal_insulation)}</p></section><section className="panel spacecraft-section"><h2>Shielding</h2><p className="spacecraft-prose">{shown(specification?.shielding)}</p></section>
  </>;
}

function route() {
  const match = window.location.hash.match(/^#spacecraft(?:\/(\d+)(?:\/modules\/(\d+))?)?$/);
  return { spacecraftId: match?.[1] ? Number(match[1]) : null, moduleId: match?.[2] ? Number(match[2]) : null };
}

export default function SpacecraftCatalog({ request, canManage }: { request: Request; canManage: boolean }) {
  const [selection, setSelection] = useState(route), [revision, setRevision] = useState(0), [notice, setNotice] = useState('');
  const [form, setForm] = useState<{ module: boolean; initial?: Spacecraft | SpacecraftModule } | null>(null);
  const [deleting, setDeleting] = useState<Spacecraft | SpacecraftModule | null>(null), [busy, setBusy] = useState(false), [deleteError, setDeleteError] = useState(''), [moduleTotal, setModuleTotal] = useState<number | null>(null);
  const { spacecraftId, moduleId } = selection;
  const refresh = () => setRevision(value => value + 1);
  const craft = useRecord<Spacecraft>(request, spacecraftId ? `/v1/spacecraft/${spacecraftId}` : null, revision);
  const module = useRecord<SpacecraftModule>(request, spacecraftId && moduleId ? `/v1/spacecraft/${spacecraftId}/modules/${moduleId}` : null, revision);
  useEffect(() => {
    const update = () => { setSelection(route()); setForm(null); setDeleting(null); setModuleTotal(null); };
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  useEffect(() => { if (notice) { const timer = setTimeout(() => setNotice(''), 5000); return () => clearTimeout(timer); } }, [notice]);
  const confirmDelete = (record: Spacecraft | SpacecraftModule) => { setDeleteError(''); setDeleting(record); };
  const heading = (record: Spacecraft | SpacecraftModule) => <div className="page-heading"><div><div className="eyebrow">{moduleId ? 'SPACECRAFT MODULE' : 'SPACECRAFT'}</div><h1>{record.name}</h1></div>{canManage && <div className="actions"><button className="secondary" onClick={() => setForm({ module: Boolean(moduleId), initial: record })}>Edit {moduleId ? 'module' : 'spacecraft'}</button><button className="secondary danger" onClick={() => confirmDelete(record)}>Delete {moduleId ? 'module' : 'spacecraft'}</button></div>}</div>;
  return <section className="spacecraft-catalog">{notice && <div className="toast" role="status">{notice}</div>}
    {!spacecraftId ? <><div className="page-heading"><h1>Spacecraft</h1>{canManage && <button onClick={() => setForm({ module: false })}>Add spacecraft</button>}</div><Collection<Spacecraft> request={request} path="/v1/spacecraft" revision={revision} canManage={canManage} onEdit={initial => setForm({ module: false, initial })}/></> : <>
      <a className="link back" href={moduleId ? craftLink(spacecraftId) : craftLink()}>{moduleId ? 'Back to spacecraft' : 'All spacecraft'}</a>
      <LoadingError loading={craft.loading || module.loading} error={craft.error || module.error} retry={refresh}/>
      {craft.record && !craft.error && !moduleId && <>{heading(craft.record)}<section className="panel spacecraft-section"><h2>General information</h2><Details><Detail label="Status" value={craft.record.status === 'in_use' ? 'In use' : 'Available'}/><Detail label="Maximum crew capacity (people)" value={craft.record.maximum_crew_capacity}/><Detail label="Model / class" value={craft.record.model}/><Detail label="Manufacturer" value={craft.record.manufacturer}/><Detail label="Serial number" value={craft.record.serial_number}/><Detail label="Manufactured year" value={craft.record.manufactured_year}/></Details><h3>Description</h3><p className="spacecraft-prose">{shown(craft.record.description)}</p><Reference url={craft.record.technical_reference_url}/></section>
        <section aria-label="Spacecraft modules"><div className="section-heading"><h2>Modules</h2>{canManage && <button onClick={() => setForm({ module: true })}>Add module</button>}</div><Collection<SpacecraftModule> key={spacecraftId} request={request} path={`/v1/spacecraft/${spacecraftId}/modules`} revision={revision} module canManage={canManage} onEdit={initial => setForm({ module: true, initial })} onTotal={setModuleTotal}/></section>
      </>}
      {craft.record && module.record && !module.error && moduleId && <>{heading(module.record)}<p className="muted">Spacecraft: <a href={craftLink(spacecraftId)}>{craft.record.name}</a></p><ModuleDetails module={module.record}/></>}
    </>}
    {form && canManage && <SpacecraftForm key={`${form.module}-${form.initial?.id ?? 'new'}`} request={request} spacecraftId={form.module ? spacecraftId! : undefined} initial={form.initial} onClose={() => setForm(null)} onSaved={record => {
      setForm(null); refresh(); setNotice(`${form.module ? 'Module' : 'Spacecraft'} saved successfully.`);
      window.location.hash = 'spacecraft_id' in record ? moduleLink(record.spacecraft_id, record.id) : craftLink(record.id);
    }}/>}
    {deleting && <Dialog title={`Delete ${'spacecraft_id' in deleting ? 'module' : 'spacecraft'}?`} busy={busy} onClose={() => setDeleting(null)}><p>Delete {deleting.name}? This action cannot be undone.</p>{!('spacecraft_id' in deleting) && <p>{moduleTotal ? 'Deletion is blocked while modules are linked. Delete the modules first.' : 'A spacecraft can only be deleted after all linked modules have been deleted.'}</p>}{deleteError && <div className="error" role="alert">{deleteError}</div>}<footer><button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button><button className="danger" disabled={busy || (!('spacecraft_id' in deleting) && Boolean(moduleTotal))} onClick={async () => {
      setBusy(true); setDeleteError('');
      const isModule = 'spacecraft_id' in deleting;
      try {
        await request(`/v1/spacecraft/${isModule ? (deleting as SpacecraftModule).spacecraft_id : deleting.id}${isModule ? `/modules/${deleting.id}` : ''}`, { method: 'DELETE' });
        setDeleting(null); refresh(); setNotice(`${isModule ? 'Module' : 'Spacecraft'} deleted.`);
        window.location.hash = isModule ? craftLink(spacecraftId!) : craftLink();
      } catch (failure) { setDeleteError((failure as ApiError).message); } finally { setBusy(false); }
    }}>{busy ? 'Deleting…' : 'Delete'}</button></footer></Dialog>}
  </section>;
}
