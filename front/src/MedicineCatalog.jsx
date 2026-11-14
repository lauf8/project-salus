import React, { useEffect, useState } from 'react';
import IngredientPicker from './IngredientPicker';


function CatalogForm({ request, kind, initial, onClose, onSaved }) {
  const [indications, setIndications] = useState(initial.main_indications || '');
  const [name, setName] = useState(initial.name || ''), [selected, setSelected] = useState(initial.active_ingredients || []), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const medicine = kind === 'medicines';
  return <div className="overlay" onKeyDown={event => { if (event.key === 'Escape' && !busy) onClose(); }}><section className="modal" role="dialog" aria-modal="true" aria-label={medicine ? "Medication" : "Active ingredient"}><header><h2>{initial.id ? "Edit" : "Add"} {medicine ? "medication" : "active ingredient"}</h2><button type="button" className="icon" aria-label="Close" disabled={busy} onClick={onClose}>×</button></header><form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError('');
    try { await request(`/v1/${kind}${initial.id ? `/${initial.id}` : ''}`, { method: initial.id ? 'PATCH' : 'POST', body: { name, ...(medicine ? { active_ingredient_ids: selected.map(item => item.id), main_indications: indications || null } : {}) } }); onSaved(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }}><fieldset disabled={busy}><label>Name<input autoFocus required maxLength={200} value={name} onChange={event => setName(event.target.value)}/></label>{medicine && <label>Main indications<textarea rows={3} maxLength={4000} value={indications} onChange={event => setIndications(event.target.value)} placeholder="Main conditions treated"/></label>}{medicine && <IngredientPicker request={request} selected={selected} onChange={setSelected}/>}</fieldset>{error && <div className="error" role="alert">{error}</div>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button disabled={busy}>{busy ? "Saving…" : "Save"}</button></footer></form></section></div>;
}

export default function MedicineCatalog({ request, kind, canManage }) {
  const [search, setSearch] = useState(''), [page, setPage] = useState(1), [result, setResult] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState(''), [form, setForm] = useState(null), [revision, setRevision] = useState(0), [deleting, setDeleting] = useState(null), [busy, setBusy] = useState(false);
  const medicine = kind === 'medicines';
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(''); setResult(null);
    request(`/v1/${kind}?${new URLSearchParams({ search, page, per_page: 10 })}`, { signal: controller.signal }).then(data => { if (!controller.signal.aborted) setResult(data); }).catch(err => { if (!controller.signal.aborted) setError(err.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, kind, search, page, revision]);
  return <section><div className="page-heading"><h1>{medicine ? "Medications" : "Active ingredients"}</h1>{canManage && <button onClick={() => setForm({})}>Add {medicine ? "medication" : "active ingredient"}</button>}</div><div className="toolbar"><label>Search by name<input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }}/></label><button className="secondary" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
    {error && <div className="error" role="alert">{error}</div>}{loading && <p role="status">Loading catalog…</p>}
    {result && <><div className="panel table-wrap"><table><thead><tr><th>NAME</th>{medicine && <><th>COMPOSITION</th><th>MAIN INDICATIONS</th></>}{canManage && <th>ACTIONS</th>}</tr></thead><tbody>{result.data.map(item => <tr key={item.id}><td>{item.name}</td>{medicine && <td>{item.active_ingredients.map(row => row.name).join(', ') || "No active ingredients registered"}</td>}{medicine && <td className="medicine-indications">{item.main_indications || "Not provided"}</td>}{canManage && <td><div className="actions"><button className="secondary" onClick={() => setForm(item)}>Edit {item.name}</button><button className="secondary danger" onClick={() => setDeleting(item)}>Delete {item.name}</button></div></td>}</tr>)}</tbody></table>{!result.data.length && <p className="empty">No records found.</p>}</div><div className="pagination"><span>Page {page}</span><button className="secondary" disabled={!result.pagination.has_previous} onClick={() => setPage(value => value - 1)}>Previous</button><button className="secondary" disabled={!result.pagination.has_next} onClick={() => setPage(value => value + 1)}>Next</button></div></>}
    {form && <CatalogForm request={request} kind={kind} initial={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); setRevision(value => value + 1); }}/ >}
    {deleting && <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label="Confirm deletion"><h2>Delete {deleting.name}?</h2><footer><button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button><button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await request(`/v1/${kind}/${deleting.id}`, { method: 'DELETE' }); setPage(1); setRevision(value => value + 1); } catch (err) { setError(err.message); } finally { setBusy(false); setDeleting(null); } }}>{busy ? "Deleting…" : "Delete"}</button></footer></section></div>}
  </section>;
}
