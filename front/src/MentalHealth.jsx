import React, {useEffect, useState} from 'react';
import {CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import './mental-health.css';

export const ratingFields = [
  ['happiness_level', 'Happiness', 'Very unhappy', 'Very happy'],
  ['satisfaction_level', 'Satisfaction with this day in the mission', 'Very dissatisfied', 'Very satisfied'],
  ['stress_level', 'Stress', 'Very low', 'Very high'],
  ['energy_level', 'Energy', 'Very low', 'Very high'],
  ['sleep_quality', 'Perceived sleep quality', 'Very poor', 'Very good'],
  ['workload_level', 'Workload', 'Very low', 'Very high'],
  ['isolation_level', 'Isolation', 'Very low', 'Very high'],
  ['crew_connection_level', 'Connection with the crew', 'Very disconnected', 'Very connected'],
];

function CheckInForm({record, selectedDate, base, request, onSaved}) {
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  return <form className="panel mental-form" onSubmit={async event=>{
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const body = Object.fromEntries(ratingFields.map(([field])=>[field, values.get(field) ? Number(values.get(field)) : null]));
    body.notes = values.get('notes') || null;
    setBusy(true); setError('');
    try {await request(`${base}/check-ins/${selectedDate}`, {method:'PUT', body}); await onSaved();} catch (err) {setError(err.message);} finally {setBusy(false);}
  }}>
    <h2>{record ? 'Edit daily check-in' : 'Daily check-in'} · {selectedDate}</h2>
    <p>Your journal and daily account are visible to you and psychologists assigned to this mission. They are not included in general mission reports.</p>
    <p>Sleep quality here is your perception. Existing sleep measurements are shown separately below. These responses do not generate a diagnosis or clinical score.</p>
    <div className="mental-ratings">{ratingFields.map(([field,label,low,high],index)=><label key={field}>{label}{index < 2 ? ' *' : ' (optional)'}<select aria-label={label} name={field} defaultValue={record?.[field] ?? ''} required={index < 2}><option value="">No response</option>{[1,2,3,4,5].map(value=><option key={value} value={value}>{value}{value===1 ? ` · ${low}` : value===5 ? ` · ${high}` : ''}</option>)}</select><small>1 · {low} / 5 · {high}</small></label>)}</div>
    <label>Daily account (optional)<textarea name="notes" defaultValue={record?.notes ?? ''} maxLength={20000} rows={5} placeholder="Events, concerns, or something that helped today"/></label>
    {record && <small>Created {new Date(record.created_at).toLocaleString()} · Updated {new Date(record.updated_at).toLocaleString()}</small>}
    {error && <p className="error" role="alert">{error}</p>}<button disabled={busy}>{busy ? 'Saving…' : 'Save check-in'}</button>
  </form>;
}

function FollowUpForm({record, data, base, request, onSaved, onCancel}) {
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const currentWeek = data.weeks.find(week=>week.start<=data.today && week.end>=data.today) || data.weeks.at(-1);
  const localTime = value=>{const date=new Date(value); return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);};
  return <form className="panel mental-form" onSubmit={async event=>{
    event.preventDefault(); const values=new FormData(event.currentTarget);
    const body={session_at:new Date(values.get('session_at')).toISOString(), review_period_start:values.get('review_period_start'), review_period_end:values.get('review_period_end'), session_summary:values.get('session_summary'), private_notes:values.get('private_notes')||null, agreed_actions:values.get('agreed_actions')||null, next_follow_up_on:values.get('next_follow_up_on')||null, share_agreed_actions:values.get('share_agreed_actions')==='on', share_next_follow_up:values.get('share_next_follow_up')==='on', contact_request_id:values.get('contact_request_id') ? Number(values.get('contact_request_id')) : null};
    setBusy(true);setError('');try {await request(`${base}/sessions${record?.id ? `/${record.id}` : ''}`,{method:record?.id?'PUT':'POST',body});await onSaved();}catch(err){setError(err.message);}finally{setBusy(false);}
  }}>
    <h2>{record?.id ? 'Edit follow-up' : 'Record a private conversation'}</h2>
    <label>Session time (your local time)<input type="datetime-local" name="session_at" required defaultValue={localTime(record?.session_at || new Date())}/></label>
    <div className="mental-ratings"><label>Review period start<input type="date" name="review_period_start" required defaultValue={record?.review_period_start || currentWeek?.start}/></label><label>Review period end<input type="date" name="review_period_end" required defaultValue={record?.review_period_end || currentWeek?.end}/></label></div>
    <label>Contact request<select aria-label="Contact request" name="contact_request_id" defaultValue={record?.contact_request_id || ''}><option value="">No linked request</option>{data.requests.filter(item=>item.status==='pending'||item.id===record?.contact_request_id).map(item=><option key={item.id} value={item.id}>#{item.id} · {new Date(item.created_at).toLocaleString()} · {item.status}</option>)}</select></label>
    <fieldset className="mental-private"><legend>Private · psychologists only</legend><label>Session summary<textarea name="session_summary" required maxLength={20000} rows={4} defaultValue={record?.session_summary || ''}/></label><label>Private notes<textarea name="private_notes" maxLength={20000} rows={4} defaultValue={record?.private_notes || ''}/></label></fieldset>
    <fieldset className="mental-shared"><legend>Share only with explicit consent below</legend><label>Agreed actions<textarea name="agreed_actions" maxLength={20000} rows={4} defaultValue={record?.agreed_actions || ''}/></label><label className="checkfield"><input type="checkbox" name="share_agreed_actions" defaultChecked={record?.share_agreed_actions || false}/>Share agreed actions with the astronaut</label><label>Next follow-up<input type="date" name="next_follow_up_on" defaultValue={record?.next_follow_up_on || ''}/></label><label className="checkfield"><input type="checkbox" name="share_next_follow_up" defaultChecked={record?.share_next_follow_up || false}/>Share return date with the astronaut</label></fieldset>
    {error&&<p className="error" role="alert">{error}</p>}<div className="actions"><button disabled={busy}>{busy?'Saving…':'Save follow-up'}</button><button className="secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button></div>
  </form>;
}

export default function MentalHealth({request, mission, members, role, currentUserId, names}) {
  const psychologist=role==='psychologist';
  const [roster,setRoster]=useState([]),[selected,setSelected]=useState(()=>psychologist?'':String(members.find(member=>String(member.user_id)===String(currentUserId))?.id||''));
  const [data,setData]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(false),[selectedDate,setSelectedDate]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState(''),[sessionForm,setSessionForm]=useState(null),[contactBusy,setContactBusy]=useState(false);
  const missionBase=`/v1/missions/${mission.id}/mental-health`,base=`${missionBase}/astronauts/${selected}`;
  useEffect(()=>{if(psychologist)request(`${missionBase}/astronauts`).then(setRoster).catch(err=>setError(err.message));},[request,missionBase,psychologist]);
  useEffect(()=>{if(!selected)return;let active=true;setData(null);setLoading(true);setError('');const query=new URLSearchParams();if(start)query.set('start',start);if(end)query.set('end',end);request(`${base}?${query}`).then(result=>{if(active){setData(result);setSelectedDate(previous=>previous||result.today);}}).catch(err=>{if(active)setError(err.message);}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[request,base,selected,start,end]);
  async function reload(){const query=new URLSearchParams();if(start)query.set('start',start);if(end)query.set('end',end);const result=await request(`${base}?${query}`);setData(result);setSelectedDate(previous=>previous||result.today);if(psychologist)setRoster(await request(`${missionBase}/astronauts`));}
  const chosen=data?.check_ins.find(item=>item.check_in_date===selectedDate);
  const chartData=data?.days.map(day=>({...day,...data.check_ins.find(item=>item.check_in_date===day.date)}));
  const colors=['#2563eb','#059669','#dc2626','#a16207','#7c3aed','#db2777','#475569','#0891b2'];
  return <section className="mental-health"><div className="section-heading"><div><h2>Mental health</h2><p>Daily journal and private weekly conversations</p></div>{!psychologist&&data&&<button disabled={contactBusy||data.requests.some(item=>item.status==='pending')} onClick={async()=>{setContactBusy(true);setError('');try{await request(`${base}/requests`,{method:'POST'});await reload();setNotice('Your conversation request has been recorded.');}catch(err){setError(err.message);}finally{setContactBusy(false);}}}>{data.requests.some(item=>item.status==='pending')?'Conversation requested':'Request a conversation'}</button>}</div>
    {psychologist&&<><h3>Astronauts under your responsibility</h3><div className="mental-roster">{roster.map(item=><button aria-label={`${names(item.user_id)} ${item.pending_requests.length} pending requests`} className={String(item.member_id)===selected?'':'secondary'} key={item.member_id} onClick={()=>{setSelected(String(item.member_id));setSelectedDate('');setSessionForm(null);setNotice('');}}><strong>{names(item.user_id)}</strong><span>{item.pending_requests.length} pending requests</span><small>{item.weeks.at(-1)?.session_ids.length?'Current week: conversation recorded':'Current week: no conversation recorded'}</small></button>)}</div>{!roster.length&&<p>No astronauts assigned to this mission.</p>}</>}
    {error&&<p className="error" role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}{loading&&<p role="status">Loading mental health records…</p>}
    {selected&&<div className="mental-ratings"><label>Period start<input type="date" value={start} onChange={event=>setStart(event.target.value)}/></label><label>Period end<input type="date" value={end} onChange={event=>setEnd(event.target.value)}/></label><button type="button" className="secondary" disabled={loading} onClick={async()=>{setError('');try{await reload();}catch(err){setError(err.message);}}}>Refresh records</button></div>}
    {data&&<><p>Mission day uses {data.timezone}. Missing days remain without a record.</p>
      <div className="mental-days" aria-label="Daily history">{data.days.map(day=><button aria-label={`${day.date} ${day.check_in_id?'Recorded':'No record'}`} key={day.date} className={`${day.date===selectedDate?'':'secondary'} ${day.check_in_id?'':'mental-missing'}`} onClick={()=>setSelectedDate(day.date)}>{day.date}<small>{day.check_in_id?'Recorded':'No record'}</small></button>)}</div>
      {!psychologist&&<><button className="secondary" onClick={()=>{setStart('');setEnd('');setSelectedDate(data.today);}}>Today's check-in</button><label>Check-in date · select a past date for a retrospective entry<input aria-label="Check-in date" type="date" max={data.today} value={selectedDate} onChange={event=>{setSelectedDate(event.target.value);if(event.target.value && (event.target.value<data.days[0]?.date||event.target.value>data.days.at(-1)?.date)){setStart(event.target.value);setEnd(event.target.value);}}}/></label>{selectedDate&&<CheckInForm key={`${selected}-${selectedDate}`} record={chosen} selectedDate={selectedDate} base={base} request={request} onSaved={async()=>{await reload();setNotice('Check-in saved.');}}/>}</>}
      <article className="panel mental-form"><h3>Daily indicator trends · 1 to 5</h3><p>Gaps indicate days or optional fields without a response. No combined score is calculated.</p><div style={{height:340}}><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="date"/><YAxis domain={[1,5]} ticks={[1,2,3,4,5]}/><Tooltip/><Legend/>{ratingFields.map(([field,label],index)=><Line key={field} dataKey={field} name={label} stroke={colors[index]} connectNulls={false} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div></article>
      {psychologist&&<article className="panel mental-form"><h3>Daily accounts</h3>{data.check_ins.map(item=><details key={item.id}><summary>{item.check_in_date}</summary>{ratingFields.map(([field,label])=><p key={field}>{label}: {item[field]??'No response'}</p>)}<p className="clinical-text">{item.notes||'No daily account'}</p></details>)}{!data.check_ins.length&&<p>No check-ins in this period.</p>}</article>}
      <article className="panel mental-form"><h3>Existing sleep records</h3>{data.sleep_observations.map(item=><p key={item.id}>{new Date(item.collected_at).toLocaleString()} · {item.indicator==='sleep_duration'?'Sleep duration':'Sleep quality'}: {item.value} {item.unit}</p>)}{!data.sleep_observations.length&&<p>No sleep measurements in this period.</p>}</article>
      <article className="panel mental-form"><h3>Conversation requests</h3>{data.requests.map(item=><p key={item.id}>#{item.id} · {new Date(item.created_at).toLocaleString()} · {item.status==='pending'?'Pending':'Fulfilled'}</p>)}{!data.requests.length&&<p>No requests.</p>}</article>
      <article className="panel mental-form"><h3>Mission weeks</h3>{data.weeks.map(week=><p key={week.start}>Week {week.week_number} · {week.start} – {week.end} · {week.session_ids.length?`${week.session_ids.length} conversation(s) recorded`:'No conversation recorded'}</p>)}</article>
      <div className="section-heading"><h3>Follow-up history</h3>{psychologist&&<button onClick={()=>setSessionForm({})}>Record conversation</button>}</div>
      {sessionForm&&<FollowUpForm key={sessionForm.id||'new'} record={sessionForm} data={data} base={base} request={request} onCancel={()=>setSessionForm(null)} onSaved={async()=>{await reload();setSessionForm(null);setNotice('Follow-up saved.');}}/>}
      {data.sessions.map(item=><article className="panel mental-form" key={item.id}><div className="section-heading"><h3>{new Date(item.session_at).toLocaleString()}</h3>{psychologist&&String(item.psychologist_user_id)===String(currentUserId)&&<button className="secondary" onClick={()=>setSessionForm(item)}>Edit follow-up</button>}</div><p>Review: {item.review_period_start} – {item.review_period_end}</p>{psychologist&&<div className="mental-private"><strong>Private · psychologists only</strong><p className="clinical-text">{item.session_summary}</p><p className="clinical-text">{item.private_notes}</p><small>Responsible: {names(item.psychologist_user_id)} · Updated by {names(item.updated_by_user_id)} · {new Date(item.updated_at).toLocaleString()}</small></div>}<div className="mental-shared"><strong>{psychologist?'Sharing settings':'Shared by your psychologist'}</strong><p className="clinical-text">Agreed actions: {item.agreed_actions||'No actions shared'}{psychologist&&` · ${item.share_agreed_actions?'Shared':'Private'}`}</p><p>Next follow-up: {item.next_follow_up_on||'No date shared'}{psychologist&&` · ${item.share_next_follow_up?'Shared':'Private'}`}</p></div></article>)}
    </>}
  </section>;
}
