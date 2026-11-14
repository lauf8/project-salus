import React, { useEffect, useState } from 'react';
import AstronautPicker from './AstronautPicker';

export default function MissionCreateForm({ request, onClose, onSaved, currentUserId }) {
  const [crewSize, setCrewSize] = useState(''), [astronauts, setAstronauts] = useState([]);
  const [spacecraft, setSpacecraft] = useState([]), [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function refresh() {
    const rows = [];
    for (let page = 1; ; page++) {
      const result = await request(`/v1/spacecraft?page=${page}&per_page=100`);
      rows.push(...result.data.filter(item => item.status === 'available'));
      if (!result.pagination.has_next) break;
    }
    setSpacecraft(rows);
    setSelected(value => rows.some(item => String(item.id) === value) ? value : '');
  }
  useEffect(() => { refresh().catch(err => setError(err.message)).finally(() => setLoading(false)); }, []);
  const capacity = spacecraft.find(item => String(item.id) === selected)?.maximum_crew_capacity;
  const validCrew = Number.isInteger(Number(crewSize)) && Number(crewSize) > 0 && Number(crewSize) <= 2147483647 && (!capacity || Number(crewSize) <= capacity) && astronauts.length <= Number(crewSize);
  return <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label="New mission"><header><h2>New mission</h2><button className="icon" disabled={busy} onClick={onClose} aria-label="Close">×</button></header><form onSubmit={async event => {
    event.preventDefault();
    if (!selected || !validCrew) return;
    const data = new FormData(event.currentTarget);
    const body = { name: data.get('name'), planned_launch_at: new Date(data.get('planned_launch_at')).toISOString(), spacecraft_id: Number(selected), crew_size: Number(crewSize), astronaut_ids: astronauts.map(user => user.id) };
    setBusy(true); setError('');
    try { await request('/v1/missions', { method: 'POST', body }); await onSaved(); onClose(); }
    catch (err) { setError(err.message); if (err.status === 409) { try { await refresh(); } catch (refreshError) { setError(`${err.message} ${refreshError.message}`); } } }
    finally { setBusy(false); }
  }}><label>Mission name<input name="name" required maxLength={200}/></label><label>Planned launch<input name="planned_launch_at" type="datetime-local" required/></label><label>Spacecraft<select name="spacecraft_id" required disabled={loading || busy} value={selected} onChange={event => setSelected(event.target.value)}><option value="" disabled>Select a spacecraft</option>{spacecraft.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{loading ? <p role="status">Loading spacecraft…</p> : !spacecraft.length && <p role="status">No spacecraft available.</p>}<label>Planned crew size<input name="crew_size" type="number" min={Math.max(1, astronauts.length)} max={capacity || 2147483647} step="1" required value={crewSize} onChange={event => setCrewSize(event.target.value)}/></label><p>{astronauts.length} astronauts selected · Spacecraft capacity: {capacity ?? 'Not specified'}</p>{crewSize && !validCrew && <p role="alert">Crew size must fit the spacecraft capacity and include all selected astronauts.</p>}<AstronautPicker request={request} excludedIds={[Number(currentUserId), ...astronauts.map(user => user.id)]} disabled={busy || !validCrew || astronauts.length >= Number(crewSize)} onAdd={user => setAstronauts(rows => [...rows, user])}/>{astronauts.length > 0 && <ul>{astronauts.map(user => <li key={user.id}>{user.name} <button type="button" className="link" disabled={busy} onClick={() => setAstronauts(rows => rows.filter(row => row.id !== user.id))}>Remove <span className="sr-only">{user.name}</span></button></li>)}</ul>}{error && <div className="error" role="alert">{error}</div>}<footer><button type="button" className="secondary" disabled={busy} onClick={onClose}>Cancel</button><button disabled={busy || loading || !selected || !validCrew}>{busy ? 'Saving…' : 'Save'}</button></footer></form></section></div>;
}
