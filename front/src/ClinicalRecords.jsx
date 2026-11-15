import React, { useEffect, useState } from 'react';
import './clinical-records.css';

const time = value => value ? new Date(value).toLocaleString('en-US') : 'Not recorded';
const localNow = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);

async function pages(request, path) {
  const first = await request(`${path}${path.includes('?') ? '&' : '?'}per_page=100`);
  const rows = [...first.data];
  for (let page = 2; page <= first.pagination.total_pages; page++) {
    rows.push(...(await request(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`)).data);
  }
  return rows;
}

export function ActiveHealthBanner({ request, user, enabled, onOpen }) {
  const [rows, setRows] = useState([]), [assessments, setAssessments] = useState([]), [error, setError] = useState('');
  useEffect(() => {
    if (!enabled || !user?.id) return;
    let active = true;
    const load = () => Promise.all([pages(request, `/v1/health/astronauts/${user.id}/occurrences?active=true`), pages(request, `/v1/health/astronauts/${user.id}/assessments`)]).then(([data, reports]) => {
      if (active) { setRows(data); setAssessments(reports.filter(row => row.report.hypotheses?.length > 0).slice(0, 3)); setError(''); }
    }).catch(e => active && setError(e.message));
    load();
    const timer = setInterval(load, 30000);
    window.addEventListener('clinical-records-changed', load);
    return () => { active = false; clearInterval(timer); window.removeEventListener('clinical-records-changed', load); };
  }, [request, user?.id, enabled]);
  if (!enabled) return null;
  if (!rows.length && !assessments.length && !error) return null;
  return <aside className="clinical-active-banner" aria-label="Active health problems">{error && <p className="error" role="alert">Unable to refresh active health problems: {error}</p>}{rows.length > 0 && <strong>Active health problems · awaiting medical recovery confirmation</strong>}{rows.map(row => <p key={row.id}>{row.icd_code && `${row.icd_code} · `}{row.condition_name} · Started {time(row.start_at)}</p>)}{assessments.map(row => <div key={row.id}><strong>Individual health assessment · approved by flight surgeon · {time(row.created_at)}</strong>{row.report.hypotheses.map((hypothesis, index) => <p key={index}>{hypothesis.condition} · {hypothesis.reasoning}</p>)}<p>{row.review_note}</p></div>)}<button className="secondary" onClick={onOpen}>Open health record</button></aside>;
}

function Report({ report }) {
  return <div className="clinical-report"><p>Mission day: {report.mission_day ?? 'Actual start not recorded'} · Assessment cutoff: {time(report.cutoff)}</p><p>Disease probability: unavailable · {report.generation_status || 'Recorded measurements'}</p>
    {report.missing_indicators?.length > 0 && <p>Missing vital signs: {report.missing_indicators.join(', ')}</p>}
    <div className="table-wrap"><table><caption>Individual measurements and previous readings</caption><thead><tr><th>Indicator</th><th>Value</th><th>Collected</th><th>Context</th></tr></thead><tbody>{report.measurements.map(row => <tr key={row.id}><td>{row.indicator}{row.previous ? ' · previous' : ''}</td><td>{row.value ?? row.category ?? `${row.systolic}/${row.diastolic}`} {row.unit}</td><td>{time(row.collected_at)}</td><td>{row.activity} · {row.signal_quality} signal{row.stale ? ' · outside freshness window' : ''} · {row.evaluation_status}</td></tr>)}</tbody></table></div>
    {report.active_alerts?.map(row => <p key={row.id}><strong>{row.severity} · {row.indicator}</strong> {row.reason}</p>)}
    {report.active_occurrences?.map(row => <p key={row.id}>Reported: {row.condition} · {row.symptoms} · {row.description}</p>)}
    {report.medication_uses?.map(row => <p key={row.id}>Medication: {row.medicine} · {row.dose} · {time(row.taken_at)} · {row.reason} · Directed by {row.instructed_by}</p>)}
    {report.hypotheses?.map((row, index) => <article className="panel" key={index}><h4>Screening hypothesis: {row.condition}</h4><p>{row.reasoning}</p><p>Measurements: {row.observation_ids.join(', ')} · Evidence passages: {row.citation_ids.join(', ')}</p></article>)}
    {report.sources?.map(row => <details key={row.id}><summary>NASA passage {row.id} · {row.title} · page {row.page ?? row.section} · {row.revision}</summary><p>{row.content}</p><a href={row.source_url} target="_blank" rel="noreferrer">Original NASA source</a></details>)}
    <ul>{report.limitations.map(text => <li key={text}>{text}</li>)}</ul>
  </div>;
}

export default function ClinicalRecords({ request, astronautId, missionId, canResolve, users = [] }) {
  const [records, setRecords] = useState([]), [medications, setMedications] = useState([]), [assessments, setAssessments] = useState([]), [report, setReport] = useState(null);
  const [revision, setRevision] = useState(0), [error, setError] = useState(''), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [form, setForm] = useState('');
  const [query, setQuery] = useState(''), [codes, setCodes] = useState([]), [codePage, setCodePage] = useState(1), [codeNext, setCodeNext] = useState(false), [selectedCode, setSelectedCode] = useState(null);
  const [medicineQuery, setMedicineQuery] = useState(''), [medicines, setMedicines] = useState([]);
  const root = `/v1/health/astronauts/${astronautId}`, scope = `?mission_id=${missionId}`;
  useEffect(() => {
    if (!astronautId || !missionId) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError(''); setRecords([]); setMedications([]); setAssessments([]); setReport(null);
    Promise.all([pages(request, `${root}/occurrences${scope}`), pages(request, `${root}/medication-uses${scope}`), pages(request, `${root}/assessments${scope}`), request(`${root}/clinical-report${scope}`)]).then(([a, b, c, d]) => {
      if (active) { setRecords(a); setMedications(b); setAssessments(c); setReport(d); }
    }).catch(e => active && setError(e.message)).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [request, astronautId, missionId, revision]);
  useEffect(() => {
    if (form !== 'occurrence') return;
    const controller = new AbortController();
    const timer = setTimeout(() => request(`/v1/health/icd10?search=${encodeURIComponent(query)}&page=${codePage}`, { signal: controller.signal }).then(data => { setCodes(data.data); setCodeNext(data.pagination.has_next); }).catch(e => { if (e.name !== 'AbortError') setError(e.message); }), 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [request, query, codePage, form]);
  useEffect(() => {
    if (form !== 'medication') return;
    const controller = new AbortController();
    const timer = setTimeout(() => request(`/v1/medicines?search=${encodeURIComponent(medicineQuery)}&per_page=100`, { signal: controller.signal }).then(data => setMedicines(data.data)).catch(e => { if (e.name !== 'AbortError') setError(e.message); }), 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [request, medicineQuery, form]);
  async function mutate(path, body) {
    setBusy(true); setError('');
    try { await request(path, { method: 'POST', body }); setForm(''); setRevision(value => value + 1); window.dispatchEvent(new Event('clinical-records-changed')); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault();
    const data = new FormData(event.currentTarget), body = Object.fromEntries(data);
    if (form === 'occurrence') {
      body.mission_id = Number(missionId); body.start_at = new Date(body.start_at).toISOString(); body.icd_code = selectedCode?.code || null;
      if (selectedCode) body.condition_name = selectedCode.name;
      await mutate(`${root}/occurrences`, body);
    } else if (form === 'medication') {
      body.mission_id = Number(missionId); body.medicine_id = Number(body.medicine_id); body.taken_at = new Date(body.taken_at).toISOString(); body.occurrence_id = body.occurrence_id ? Number(body.occurrence_id) : null;
      await mutate(`${root}/medication-uses`, body);
    } else if (form.startsWith('recover:')) {
      body.finish_at = new Date(body.finish_at).toISOString();
      await mutate(`${root}/occurrences/${form.split(':')[1]}/recover${scope}`, body);
    } else {
      await mutate(`${root}/assessments/${form.split(':')[1]}/review${scope}`, body);
    }
  }
  if (!astronautId || !missionId) return <p>Select a mission to record health problems and medication consumption.</p>;
  const name = id => users.find(row => row.id === id)?.name || `User #${id}`;
  return <section className="clinical-records panel"><div className="section-heading"><div><h2>Health problems & medication use</h2><p>Reported conditions remain active until the flight surgeon confirms recovery.</p></div><button className="secondary" disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh records</button></div>
    {error && <p className="error" role="alert">{error}</p>}{loading && <p role="status">Loading clinical records…</p>}
    {!loading && <><div className="clinical-actions"><button disabled={busy} onClick={() => { setSelectedCode(null); setForm('occurrence'); }}>Report a health problem</button><button disabled={busy} onClick={() => setForm('medication')}>Record medication taken</button>{canResolve && <button disabled={busy} onClick={() => mutate(`${root}/assessments`, { mission_id: Number(missionId) })}>{busy ? 'Preparing assessment…' : 'Generate NASA health assessment'}</button>}</div>
      {[...records.filter(row => row.status === 'active'), ...records.filter(row => row.status !== 'active')].map(row => <article key={row.id} className={row.status === 'active' ? 'clinical-active-record' : 'clinical-history-record'}><h3>{row.icd_code && `${row.icd_code} · `}{row.condition_name} · {row.status}</h3><p>Reported condition · Started {time(row.start_at)} · Finished {time(row.finish_at)}</p><p>{row.description}</p><p>Symptoms: {row.symptoms}</p><small>Recorded by {name(row.recorded_by_user_id)} · {time(row.recorded_at)}</small>{row.resolution_note && <p>Recovery confirmed by {name(row.resolved_by_user_id)} · {row.resolution_note}</p>}{canResolve && row.status === 'active' && <button disabled={busy} onClick={() => setForm(`recover:${row.id}`)}>Confirm recovery</button>}</article>)}
      {!records.length && <p>No health problems recorded.</p>}
      <details><summary>Medication consumption history ({medications.length})</summary>{medications.map(row => <article className="clinical-history-record" key={row.id}><h3>{row.medicine_name} · {row.dose}</h3><p>Taken by {name(row.astronaut_id)} · {time(row.taken_at)}</p><p>Reason: {row.reason} · Directed by: {row.instructed_by}</p><small>Recorded by {name(row.recorded_by_user_id)} · {time(row.recorded_at)}{row.occurrence_id ? ` · Health occurrence #${row.occurrence_id}` : ''}</small></article>)}</details>
      {report && <details><summary>Current individual health report</summary><Report report={report}/></details>}
      {assessments.map(row => <details key={row.id}><summary>NASA health assessment #{row.id} · {row.status} · {time(row.created_at)}</summary><Report report={row.report}/>{row.review_note && <p>Flight surgeon review: {row.review_note} · {name(row.reviewed_by_user_id)} · {time(row.reviewed_at)}</p>}{canResolve && row.status === 'pending' && <button disabled={busy} onClick={() => setForm(`review:${row.id}`)}>Review for astronaut delivery</button>}</details>)}
    </>}
    {form && <div className="overlay"><section className="modal" role="dialog" aria-modal="true" aria-label={form === 'occurrence' ? 'Report a health problem' : form === 'medication' ? 'Record medication taken' : 'Medical review'}><h2>{form === 'occurrence' ? 'Report a health problem' : form === 'medication' ? 'Record medication taken' : 'Medical review'}</h2><form onSubmit={submit}>
      {form === 'occurrence' && <><p>A selected condition is a report for medical evaluation.</p><label>Search WHO ICD-10 in English<input value={query} onChange={event => { setQuery(event.target.value); setCodePage(1); }}/></label><label>WHO ICD-10 code (optional)<select aria-label="WHO ICD-10 code" value={selectedCode?.code || ''} onChange={event => setSelectedCode(codes.find(row => row.code === event.target.value) || null)}><option value="">Describe without a code</option>{selectedCode && !codes.some(row => row.code === selectedCode.code) && <option value={selectedCode.code}>{selectedCode.code} · {selectedCode.name}</option>}{codes.map(row => <option key={row.code} value={row.code} disabled={!row.selectable}>{row.code} · {row.name}</option>)}</select></label><div className="clinical-actions"><button type="button" className="secondary" disabled={codePage === 1} onClick={() => setCodePage(value => value - 1)}>Previous codes</button><span>Page {codePage}</span><button type="button" className="secondary" disabled={!codeNext} onClick={() => setCodePage(value => value + 1)}>Next codes</button></div><label>Condition / health problem<input key={selectedCode?.code || 'custom'} name="condition_name" defaultValue={selectedCode?.name || ''} readOnly={Boolean(selectedCode)} required maxLength={2000}/></label><label>Description<textarea name="description" required maxLength={6000}/></label><label>Symptoms<textarea name="symptoms" required maxLength={4000}/></label><label>Start at<input name="start_at" type="datetime-local" defaultValue={localNow()} required/></label></>}
      {form === 'medication' && <><label>Search medication<input value={medicineQuery} onChange={event => setMedicineQuery(event.target.value)}/></label><label>Medication<select aria-label="Medication" name="medicine_id" required><option value="">Select medication</option>{medicines.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>Taken at<input name="taken_at" type="datetime-local" required defaultValue={localNow()}/></label><label>Dose and route<input name="dose" required maxLength={250} placeholder="Describe the dose actually taken"/></label><label>Reason<textarea name="reason" required maxLength={4000}/></label><label>Who instructed you to take it?<input name="instructed_by" required maxLength={250} placeholder="Name / role, or self-directed"/></label><label>Related health problem (optional)<select aria-label="Related health problem (optional)" name="occurrence_id"><option value="">None</option>{records.map(row => <option key={row.id} value={row.id}>{row.condition_name} · {row.status}</option>)}</select></label></>}
      {form.startsWith('recover:') && <><label>Finish at<input name="finish_at" type="datetime-local" required defaultValue={localNow()}/></label><label>Recovery assessment<textarea name="resolution_note" required maxLength={6000}/></label></>}
      {form.startsWith('review:') && <><label>Decision<select name="decision"><option value="approved">Approve for astronaut</option><option value="rejected">Reject</option></select></label><label>Clinical review and instructions<textarea name="note" required maxLength={6000}/></label></>}
      {error && <p className="error" role="alert">{error}</p>}<footer><button type="button" className="secondary" disabled={busy} onClick={() => setForm('')}>Cancel</button><button disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></footer>
    </form></section></div>}
  </section>;
}
