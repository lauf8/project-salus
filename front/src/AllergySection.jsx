import React, { useEffect, useState } from 'react';
import IngredientPicker from './IngredientPicker';
import { allergyStatus } from './allergies';

export default function AllergySection({ request, crewMemberId, missionId }) {
  const [record, setRecord] = useState(null), [selected, setSelected] = useState([]), [completed, setCompleted] = useState(false), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0), [editing, setEditing] = useState(false), [saved, setSaved] = useState(false);
  const path = `/v1/health/astronauts/${crewMemberId}/allergies${missionId ? `?mission_id=${missionId}` : ''}`;
  useEffect(() => {
    const controller = new AbortController();
    setRecord(null); setLoading(true); setError(''); setEditing(false); setSaved(false);
    request(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) { setRecord(data); setSelected(data.active_ingredients); setCompleted(data.allergy_screening_completed); }
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [request, path, revision]);
  return <section className="panel allergy-section" aria-label="Crew member allergies"><div className="section-heading"><div><h2>Allergies</h2><p>Active ingredient allergy records.</p></div>{record?.can_edit && !editing && <button className="secondary" onClick={() => { setEditing(true); setSaved(false); }}>Edit allergies</button>}</div>
    {loading && <p role="status">Loading allergies…</p>}{error && <div className="error" role="alert">{error}{!record && <button className="link" onClick={() => setRevision(value => value + 1)}>Try again</button>}</div>}{saved && <p role="status">Allergies and screening saved.</p>}
    {record && <><span className={`badge ${record.allergy_screening_completed ? 'completed' : 'pending'}`}>{allergyStatus(record)}</span>
      {editing ? <form onSubmit={async event => {
        event.preventDefault(); setBusy(true); setError('');
        try { const data = await request(path, { method: 'PUT', body: { allergy_screening_completed: completed, active_ingredient_ids: selected.map(item => item.id) } }); setRecord(data); setEditing(false); setSaved(true); }
        catch (err) { setError(err.message); } finally { setBusy(false); }
      }}><fieldset disabled={busy}><IngredientPicker request={request} selected={selected} onChange={setSelected}/><label className="checkfield"><input type="checkbox" checked={completed} onChange={event => setCompleted(event.target.checked)}/>Screening completed</label></fieldset><div className="actions"><button type="button" className="secondary" disabled={busy} onClick={() => { setEditing(false); setError(''); setSelected(record.active_ingredients); setCompleted(record.allergy_screening_completed); }}>Cancel</button><button disabled={busy}>{busy ? "Saving…" : "Save allergies"}</button></div></form> : <ul>{record.active_ingredients.map(item => <li key={item.id}>{item.name}</li>)}</ul>}
    </>}
  </section>;
}
