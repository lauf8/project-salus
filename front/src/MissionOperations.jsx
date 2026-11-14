import React, {useEffect, useState} from 'react';
import {missionRoles} from './user-profiles';

export default function MissionOperations({request, mission}) {
  const [data,setData]=useState(null),[error,setError]=useState('');
  useEffect(()=>{let active=true;request(`/v1/missions/${mission.id}/operations`).then(result=>{if(active)setData(result);}).catch(err=>{if(active)setError(err.message);});return()=>{active=false;};},[request,mission.id]);
  return <section className="panel" style={{padding:24}}><h2>Mission operations</h2><p>Operational information available to assigned observers and mission participants.</p>{error&&<p className="error" role="alert">{error}</p>}{data?<><p>Status: {data.status}</p><p>Planned crew: {data.crew_size??'Not specified'}</p><table><thead><tr><th>Responsibility</th><th>Participants</th></tr></thead><tbody>{Object.entries(data.participants_by_role).map(([role,count])=><tr key={role}><td>{missionRoles[role]||role}</td><td>{count}</td></tr>)}</tbody></table></>:!error&&<p role="status">Loading operations…</p>}</section>;
}
