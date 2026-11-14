import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowRight, RefreshCw } from 'lucide-react';
import {
  activityLabels, doseRows, doseSourceLabels, eventSummary, eventTypeLabels, fluxSeries, followUpStatusLabels, isoFromLocal,
  organLabels, periodLabels, radiationRuleLabels, radiationSymptomLabels, solarRadiationScale, sortRadiationAlerts, timelineRows, windowState,
} from './radiation.js';
import './radiation.css';

const severityLabels = { attention: 'Caution', urgent: 'Urgent', critical: 'Critical' };
const when = value => value ? new Date(value).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC' : '—';
const localInput = value => { const date = value ? new Date(value) : new Date(); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };

function Feedback({ error, notice }) {
  return <>{error && <p className="error" role="alert">{error}</p>}{notice && <p role="status" className="radiation-notice">{notice}</p>}</>;
}

function useAction(onDone) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const run = useCallback(async (action, message) => {
    setBusy(true); setError(''); setNotice('');
    try { await action(); setNotice(message); await onDone?.(); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }, [onDone]);
  return { busy, error, notice, run };
}

function EventCard({ event }) {
  return <div className={`radiation-event radiation-${event.event_type.toLowerCase()}`}>
    <small>{eventTypeLabels[event.event_type]} · {event.health_relevance === 'exposure' ? 'exposure' : 'precursor'}</small>
    <strong>{event.event_type === 'FLR' ? event.flare_class || 'Flare' : event.event_type}</strong>
    <span>{eventSummary(event)}</span>
    <time>{when(event.start_time)}</time>
    {event.link && <a href={event.link} target="_blank" rel="noreferrer">DONKI record</a>}
  </div>;
}

function Chains({ chains }) {
  if (!chains.length) return <p>No flares, CMEs or SEPs imported for this mission period. Import them under Space weather sync.</p>;
  return <div className="radiation-chains">{chains.map(chain => {
    const steps = [['Flare', chain.flares], ['CME', chain.cmes], ['SEP', chain.seps]];
    return <article className="radiation-chain" key={[...chain.flares, ...chain.cmes, ...chain.seps].map(event => event.id).join('-')} aria-label={`Chain starting ${when(chain.starts_at)}`}>
      {steps.map(([label, events], index) => <React.Fragment key={label}>
        {index > 0 && <ArrowRight className="radiation-arrow" size={18} aria-hidden="true"/>}
        <div className="radiation-step"><h4>{label}</h4>{events.length ? events.map(event => <EventCard key={event.id} event={event}/>) : <p className="radiation-missing">Not linked</p>}</div>
      </React.Fragment>)}
      {chain.other_linked.length > 0 && <p className="radiation-other">Other linked DONKI records: {chain.other_linked.join(', ')}</p>}
    </article>;
  })}</div>;
}

function FluxChart({ readings }) {
  const series = useMemo(() => fluxSeries(readings).map(point => ({ ...point, flux: Math.max(point.flux, 0.01) })), [readings]);
  if (!series.length) return <p>No proton flux readings in this period. Import recent data from NOAA SWPC or simulate the flux of an SEP.</p>;
  const peak = Math.max(...series.map(point => point.flux));
  // Décadas de 0,1 pfu até a primeira potência de 10 acima do pico.
  const ticks = Array.from({ length: Math.max(2, Math.ceil(Math.log10(peak)) + 2) }, (_, index) => 10 ** (index - 1));
  return <>
    <p>Peak ≥10 MeV flux: <strong>{peak.toLocaleString('en-US', { maximumFractionDigits: 1 })} pfu</strong>{solarRadiationScale(peak) && ` · NOAA ${solarRadiationScale(peak)}`}{series.some(point => point.simulated) && ' · includes simulated readings'}</p>
    <div className="radiation-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={series}>
      <CartesianGrid strokeDasharray="3 3"/>
      <XAxis dataKey="time" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={value => new Date(value).toISOString().slice(5, 16).replace('T', ' ')}/>
      <YAxis scale="log" domain={[0.1, ticks.at(-1)]} ticks={ticks} allowDataOverflow tickFormatter={value => value >= 1 ? value.toLocaleString('en-US') : value} label={{ value: 'pfu', angle: -90, position: 'insideLeft' }}/>
      <Tooltip labelFormatter={value => when(value)} formatter={value => [`${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })} pfu`, '≥10 MeV']}/>
      {[10, 100, 1000].map((level, index) => <ReferenceLine key={level} y={level} stroke="#b45309" strokeDasharray="4 4" label={{ value: `S${index + 1}`, position: 'insideTopRight', fill: '#b45309', fontSize: 11 }}/>)}
      <Line dataKey="flux" stroke="#1d4ed8" dot={false} isAnimationActive={false}/>
    </LineChart></ResponsiveContainer></div>
  </>;
}

function Timeline({ rows }) {
  if (!rows.length) return <p>Nothing recorded in this mission period yet.</p>;
  return <ol className="radiation-timeline">{rows.map(row => <li key={row.key} className={`radiation-row radiation-row-${row.type.toLowerCase()}`}>
    <time>{when(row.at)}{row.end && ` → ${when(row.end)}`}</time>
    <strong>{row.title}{row.kind === 'event' && ` · ${row.role === 'exposure' ? 'exposure' : 'precursor'}`}</strong>
    {row.detail && <span>{row.detail}</span>}
  </li>)}</ol>;
}

function AlertList({ alerts, mission, request, names, onChange }) {
  const { busy, error, notice, run } = useAction(onChange);
  const [resolving, setResolving] = useState(null);
  if (!alerts.length) return <p>No active radiation alerts.</p>;
  return <><Feedback error={error} notice={notice}/><ul className="radiation-alerts">{sortRadiationAlerts(alerts).map(alert => <li key={alert.id} className={`radiation-alert radiation-${alert.severity}`}>
    <div><span className="badge">{severityLabels[alert.severity]}</span> <strong>{radiationRuleLabels[alert.rule_id]}</strong> · {names(alert.astronaut_id)} · {alert.status === 'acknowledged' ? 'Acknowledged · still active' : 'Active'}</div>
    <p>{alert.reason}</p>
    <div className="actions">
      {alert.status === 'open' && <button className="secondary" disabled={busy} onClick={() => run(() => request(`/v1/radiation/missions/${mission.id}/alerts/${alert.id}/acknowledge`, { method: 'POST' }), 'Alert acknowledged. It stays active until the flight surgeon resolves it.')}>Acknowledge</button>}
      {alert.can_resolve && resolving !== alert.id && <button className="secondary" disabled={busy} onClick={() => setResolving(alert.id)}>Resolve</button>}
    </div>
    {resolving === alert.id && <form className="radiation-inline" onSubmit={event => { event.preventDefault(); const note = new FormData(event.currentTarget).get('note'); run(async () => { await request(`/v1/radiation/missions/${mission.id}/alerts/${alert.id}/resolve`, { method: 'POST', body: { note } }); setResolving(null); }, 'Alert resolved.'); }}>
      <label>Resolution note<textarea name="note" required maxLength={4000} rows={2}/></label>
      <button disabled={busy}>Confirm resolution</button><button type="button" className="secondary" onClick={() => setResolving(null)}>Cancel</button>
    </form>}
  </li>)}</ul></>;
}

function ActivityPanel({ mission, activities, crew, canRecordFor, request, names, onChange }) {
  const { busy, error, notice, run } = useAction(onChange);
  const allowed = crew.filter(member => canRecordFor(member.user_id));
  return <>
    {allowed.length > 0 && <form className="radiation-form" onSubmit={event => {
      event.preventDefault(); const data = new FormData(event.currentTarget);
      const body = { astronaut_id: Number(data.get('astronaut_id')), activity_type: data.get('activity_type'), started_at: isoFromLocal(data.get('started_at')), ended_at: isoFromLocal(data.get('ended_at')), note: data.get('note') || null };
      run(() => request(`/v1/radiation/missions/${mission.id}/crew-activities`, { method: 'POST', body }), 'Activity recorded. An EVA that overlaps an SEP opens the 48 h observation window.');
    }}>
      <label>Astronaut<select name="astronaut_id" required>{allowed.map(member => <option key={member.user_id} value={member.user_id}>{names(member.user_id)}</option>)}</select></label>
      <label>Activity<select name="activity_type" defaultValue="eva">{Object.entries(activityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Start (your local time)<input type="datetime-local" name="started_at" required defaultValue={localInput()}/></label>
      <label>End (optional)<input type="datetime-local" name="ended_at"/></label>
      <label>Note<input name="note" maxLength={4000}/></label>
      <button disabled={busy}>{busy ? 'Saving…' : 'Record activity'}</button>
    </form>}
    <Feedback error={error} notice={notice}/>
    <div className="table-wrap"><table><thead><tr><th>ASTRONAUT</th><th>ACTIVITY</th><th>START</th><th>END</th><th></th></tr></thead><tbody>
      {[...activities].reverse().map(activity => <tr key={activity.id}><td>{names(activity.astronaut_id)}</td><td>{activityLabels[activity.activity_type]}</td><td>{when(activity.started_at)}</td><td>{activity.ended_at ? when(activity.ended_at) : 'In progress'}</td>
        <td>{!activity.ended_at && canRecordFor(activity.astronaut_id) && <button className="secondary" disabled={busy} onClick={() => run(() => request(`/v1/radiation/missions/${mission.id}/crew-activities/${activity.id}/end`, { method: 'POST', body: { ended_at: new Date().toISOString() } }), 'Activity ended.')}>End now</button>}</td></tr>)}
      {!activities.length && <tr><td colSpan={5}>No activities recorded.</td></tr>}
    </tbody></table></div>
  </>;
}

function FollowUpCard({ followUp, mission, canReport, canManage, request, names, onChange }) {
  const { busy, error, notice, run } = useAction(onChange);
  const [closing, setClosing] = useState(false);
  const base = `/v1/radiation/missions/${mission.id}/follow-ups/${followUp.id}`;
  return <article className={`panel radiation-follow-up ${followUp.window_active ? 'radiation-window-active' : ''}`}>
    <div className="section-heading"><div><h3>{names(followUp.astronaut_id)} · {followUp.event_activity_id}</h3><p>{when(followUp.opened_at)} → {when(followUp.window_ends_at)} · {followUp.was_on_eva ? 'On EVA during the SEP' : 'Inside the spacecraft'} · {windowState(followUp)}</p></div><span className="badge">{followUpStatusLabels[followUp.status]}</span></div>
    <p>Reported symptoms: {followUp.symptoms.length ? followUp.symptoms.map(key => radiationSymptomLabels[key]).join(', ') : 'none so far'}</p>
    {followUp.reports.length > 0 && <ul className="radiation-reports">{followUp.reports.map(report => <li key={report.id}><time>{when(report.reported_at)}</time> · {report.symptoms.map(key => radiationSymptomLabels[key]).join(', ') || 'No symptoms'}{report.note && ` · ${report.note}`}{report.observation_id && ' · from a health measurement'}</li>)}</ul>}
    {followUp.notes && <p className="clinical-text">{followUp.notes}</p>}
    <Feedback error={error} notice={notice}/>
    {followUp.status === 'open' && canReport && <form className="radiation-inline" onSubmit={event => {
      event.preventDefault(); const form = event.currentTarget, data = new FormData(form);
      const body = { symptoms: data.getAll('symptoms'), reported_at: isoFromLocal(data.get('reported_at')), note: data.get('note') || null };
      run(async () => { await request(`${base}/reports`, { method: 'POST', body }); form.reset(); }, 'Symptoms recorded.');
    }}>
      <fieldset><legend>Symptoms since the SEP</legend>{Object.entries(radiationSymptomLabels).map(([value, label]) => <label className="checkfield" key={value}><input type="checkbox" name="symptoms" value={value}/>{label}</label>)}</fieldset>
      <label>Observed at (your local time)<input type="datetime-local" name="reported_at" defaultValue={localInput()}/></label>
      <label>Note<input name="note" maxLength={4000}/></label>
      <button disabled={busy}>Record symptoms</button>
    </form>}
    {followUp.status === 'open' && canManage && (closing ? <form className="radiation-inline" onSubmit={event => {
      event.preventDefault(); const data = new FormData(event.currentTarget);
      run(() => request(`${base}/close`, { method: 'POST', body: { status: data.get('status'), notes: data.get('notes') } }), 'Follow-up closed.');
    }}>
      <label>Outcome<select name="status"><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label>
      <label>Clinical notes<textarea name="notes" required maxLength={4000} rows={2}/></label>
      <button disabled={busy}>Close follow-up</button><button type="button" className="secondary" onClick={() => setClosing(false)}>Cancel</button>
    </form> : <button className="secondary" onClick={() => setClosing(true)}>Close follow-up</button>)}
  </article>;
}

function DosePanel({ mission, crew, canManage, currentUserId, request, names, events, onChange }) {
  const visible = canManage ? crew : crew.filter(member => String(member.user_id) === String(currentUserId));
  const [astronaut, setAstronaut] = useState(visible[0] ? String(visible[0].user_id) : '');
  const [summary, setSummary] = useState(null), [records, setRecords] = useState([]), [loadError, setLoadError] = useState('');
  const load = useCallback(async () => {
    if (!astronaut) return;
    setLoadError('');
    try {
      const [nextSummary, page] = await Promise.all([
        request(`/v1/radiation/missions/${mission.id}/astronauts/${astronaut}/dose-summary`),
        request(`/v1/radiation/missions/${mission.id}/doses?astronaut_id=${astronaut}&per_page=100`),
      ]);
      setSummary(nextSummary); setRecords(page.data);
    } catch (err) { setLoadError(err.message); }
  }, [astronaut, mission.id, request]);
  useEffect(() => { load(); }, [load]);
  const after = useCallback(async () => { await load(); await onChange(); }, [load, onChange]);
  const { busy, error, notice, run } = useAction(after);
  const seps = events.filter(event => event.event_type === 'SEP');
  if (!visible.length) return <p>Dose records are visible to the flight surgeon and to each astronaut.</p>;
  return <>
    <label className="astronaut-select">Astronaut<select aria-label="Dose astronaut" value={astronaut} onChange={event => setAstronaut(event.target.value)}>{visible.map(member => <option key={member.user_id} value={member.user_id}>{names(member.user_id)}</option>)}</select></label>
    <Feedback error={loadError}/>
    {summary && <><p>Accumulated dose as of {when(summary.as_of)} against profile <code>{summary.profile_id}</code>. Historical NASA SP-2009-3405 limits; check the current NASA-STD-3001.</p>
      <div className="table-wrap"><table className="radiation-doses"><thead><tr><th>ORGAN</th><th>PERIOD</th><th>DOSE</th><th>LIMIT</th><th>USE OF LIMIT</th></tr></thead><tbody>{doseRows(summary).map(item => <tr key={`${item.organ}-${item.period}`}>
        <td>{organLabels[item.organ]}</td><td>{periodLabels[item.period]}</td><td>{item.total.toLocaleString('en-US', { maximumFractionDigits: 2 })} {item.unit}</td><td>{item.limit.toLocaleString('en-US')} {item.unit}</td>
        <td><div className={`radiation-meter radiation-${item.severity || 'ok'}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(item.fraction * 100)} aria-label={`${organLabels[item.organ]} ${periodLabels[item.period]}`}><span style={{ width: `${Math.min(100, item.fraction * 100)}%` }}/></div>{(item.fraction * 100).toFixed(1)}%</td>
      </tr>)}</tbody></table></div></>}
    <h4>Dose records</h4>
    <div className="table-wrap"><table><thead><tr><th>ORGAN</th><th>DOSE</th><th>PERIOD</th><th>SOURCE</th></tr></thead><tbody>
      {records.map(record => <tr key={record.id}><td>{organLabels[record.organ]}</td><td>{record.dose} {record.unit}</td><td>{when(record.period_start)} → {when(record.period_end)}</td><td>{doseSourceLabels[record.source]}</td></tr>)}
      {!records.length && <tr><td colSpan={4}>No dose records.</td></tr>}
    </tbody></table></div>
    <Feedback error={error} notice={notice}/>
    {canManage && <div className="radiation-forms">
      <form className="radiation-form" onSubmit={event => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        const organ = data.get('organ');
        const body = { astronaut_id: Number(astronaut), organ, dose: Number(data.get('dose')), unit: organ === 'cns_z_ge_10' ? 'mGy' : 'mGy-Eq', source: data.get('source'), period_start: isoFromLocal(data.get('period_start')), period_end: isoFromLocal(data.get('period_end')), event_activity_id: data.get('event') || null };
        run(() => request(`/v1/radiation/missions/${mission.id}/doses`, { method: 'POST', body }), 'Dose recorded.');
      }}>
        <h4>Record measured dose</h4>
        <label>Organ<select name="organ">{Object.entries(organLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Dose (mGy-Eq; mGy for CNS Z ≥ 10)<input type="number" name="dose" min="0" step="any" required/></label>
        <label>Source<select name="source"><option value="dosimeter">Dosimeter</option><option value="model_estimate">Model estimate</option></select></label>
        <label>Period start<input type="datetime-local" name="period_start" required/></label>
        <label>Period end<input type="datetime-local" name="period_end" required/></label>
        <label>Related SEP<select name="event"><option value="">None</option>{seps.map(event => <option key={event.id} value={event.activity_id}>{event.activity_id}</option>)}</select></label>
        <button disabled={busy}>Save dose</button>
      </form>
      <form className="radiation-form" onSubmit={event => {
        event.preventDefault(); const data = new FormData(event.currentTarget);
        const body = { start: isoFromLocal(data.get('start')), end: isoFromLocal(data.get('end')), event_activity_id: data.get('event') || null };
        run(() => request(`/v1/radiation/missions/${mission.id}/doses/simulate`, { method: 'POST', body }), 'Simulated doses generated for the crew.');
      }}>
        <h4>Simulate crew doses</h4>
        <p>Integrates the ≥10 MeV flux with each astronaut's activity (EVA, IVA or shelter). Teaching estimate, not dosimetry.</p>
        <label>Start<input type="datetime-local" name="start" required/></label>
        <label>End<input type="datetime-local" name="end" required/></label>
        <label>Related SEP<select name="event"><option value="">None</option>{seps.map(event => <option key={event.id} value={event.activity_id}>{event.activity_id}</option>)}</select></label>
        <button disabled={busy}>Simulate doses</button>
      </form>
    </div>}
  </>;
}

function FluxControls({ events, request, onChange }) {
  const { busy, error, notice, run } = useAction(onChange);
  const seps = events.filter(event => event.event_type === 'SEP');
  return <div className="radiation-forms">
    <form className="radiation-form" onSubmit={event => {
      event.preventDefault(); const window = new FormData(event.currentTarget).get('window');
      run(async () => { const result = await request('/v1/radiation/proton-flux/sync', { method: 'POST', body: { window } }); return result; }, 'NOAA SWPC readings imported.');
    }}>
      <h4>Import GOES proton flux (NOAA SWPC)</h4>
      <p>NOAA only publishes the last few days.</p>
      <label>Period<select name="window" defaultValue="1-day"><option value="6-hour">6 hours</option><option value="1-day">1 day</option><option value="3-day">3 days</option><option value="7-day">7 days</option></select></label>
      <button disabled={busy}>Import</button>
    </form>
    {seps.length > 0 && <form className="radiation-form" onSubmit={event => {
      event.preventDefault(); const data = new FormData(event.currentTarget);
      const body = { event_activity_id: data.get('event'), peak_pfu: Number(data.get('peak')), rise_hours: Number(data.get('rise')), decay_hours: Number(data.get('decay')), duration_hours: 48 };
      run(() => request('/v1/radiation/proton-flux/simulate', { method: 'POST', body }), 'Simulated proton flux stored.');
    }}>
      <h4>Simulate SEP proton flux</h4>
      <label>SEP<select name="event">{seps.map(event => <option key={event.id} value={event.activity_id}>{event.activity_id}</option>)}</select></label>
      <label>Peak ≥10 MeV flux (pfu)<input type="number" name="peak" min="11" max="1000000" defaultValue="1500" required/></label>
      <label>Rise (h)<input type="number" name="rise" min="0.5" max="47" step="0.5" defaultValue="4" required/></label>
      <label>Decay constant (h)<input type="number" name="decay" min="1" max="96" step="0.5" defaultValue="12" required/></label>
      <button disabled={busy}>Simulate flux</button>
    </form>}
    <Feedback error={error} notice={notice}/>
  </div>;
}

export default function Radiation({ request, mission, members, role, currentUserId, names, canManageCatalog }) {
  const [timeline, setTimeline] = useState(null), [readings, setReadings] = useState([]), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const next = await request(`/v1/radiation/missions/${mission.id}/timeline`);
      const query = new URLSearchParams({ start: next.start, end: next.end, limit: '5000' });
      setTimeline(next); setReadings(await request(`/v1/radiation/proton-flux?${query}`));
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }, [mission.id, request]);
  useEffect(() => { load(); }, [load]);

  const crew = members.filter(member => member.role === 'astronaut');
  const canManage = Boolean(timeline?.can_manage);
  const canRecordFor = astronautId => canManage || role === 'mission_admin' || String(astronautId) === String(currentUserId);
  const rows = useMemo(() => timelineRows(timeline), [timeline]);

  return <section className="radiation">
    <div className="section-heading"><div><h2>Space radiation</h2><p>Solar events, crew exposure and the 48 h follow-up after an SEP (NASA SP-2009-3405, ch. 5).</p></div><button className="secondary" disabled={loading} onClick={load}><RefreshCw size={16}/> Refresh</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    {loading && !timeline && <p role="status">Loading radiation data…</p>}
    {timeline && <>
      {timeline.can_view_clinical && <article className="panel radiation-panel"><h3>Radiation alerts</h3><AlertList alerts={timeline.alerts} mission={mission} request={request} names={names} onChange={load}/></article>}
      <article className="panel radiation-panel"><h3>Flare → CME → SEP</h3><p>Flares and CMEs are precursors; the SEP is the exposure event. A DONKI record alone does not mean a crew member received a relevant dose.</p><Chains chains={timeline.chains}/></article>
      <article className="panel radiation-panel"><h3>Proton flux ≥10 MeV</h3><FluxChart readings={readings}/>{canManageCatalog && <FluxControls events={timeline.events} request={request} onChange={load}/>}</article>
      <article className="panel radiation-panel"><h3>Mission timeline</h3><p>{when(timeline.start)} → {when(timeline.end)}. IVA periods are omitted.</p><Timeline rows={rows}/></article>
      <article className="panel radiation-panel"><h3>Crew activity</h3><p>Where each astronaut was: inside the spacecraft, on EVA or in the storm shelter. EVA is the critical scenario for an SEP.</p><ActivityPanel mission={mission} activities={timeline.activities} crew={crew} canRecordFor={canRecordFor} request={request} names={names} onChange={load}/></article>
      {timeline.can_view_clinical && <article className="panel radiation-panel"><h3>48 h follow-up</h3><p>Opened automatically for crew on EVA when an SEP starts. Record nausea, vomiting, loss of appetite, fatigue and skin changes.</p>
        {timeline.follow_ups.length ? [...timeline.follow_ups].reverse().map(followUp => <FollowUpCard key={followUp.id} followUp={followUp} mission={mission} canReport={canManage || String(followUp.astronaut_id) === String(currentUserId)} canManage={canManage} request={request} names={names} onChange={load}/>) : <p>No observation windows opened.</p>}
      </article>}
      <article className="panel radiation-panel"><h3>Doses and limits</h3><DosePanel mission={mission} crew={crew} canManage={canManage} currentUserId={currentUserId} request={request} names={names} events={timeline.events} onChange={load}/></article>
    </>}
  </section>;
}
