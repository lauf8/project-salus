export const accountProfiles = [
  ['is_astronaut', 'Astronaut'],
  ['is_physician', 'Physician'],
  ['is_psychologist', 'Psychologist'],
  ['is_nutritionist', 'Nutritionist'],
  ['is_nurse', 'Nurse'],
  ['is_observer', 'Observer'],
  ['is_mission_admin', 'Mission administrator'],
  ['is_global_admin', 'Global administrator'],
];
export const missionRoles = {mission_admin:'Mission administrator', flight_surgeon:'Flight surgeon', astronaut:'Astronaut', psychologist:'Psychologist', nutritionist:'Nutritionist', nurse:'Nurse', observer:'Observer'};
export function profileLabel(user) {return accountProfiles.filter(([field])=>user?.[field]).map(([,label])=>label).join(' · ') || 'Not provided';}
export function missionTabs(role, physician=false) {
  const tabs=[['operations','Operations'],['members','Crew'],['risks','Risks']];
  if(['astronaut','flight_surgeon'].includes(role))tabs.push(['checklist','Monitoring checklist']);
  if(role!=='observer')tabs.push(['nutrition','Food and hydration']);
  if(role!=='observer')tabs.push(['radiation','Radiation']);
  if(['astronaut','psychologist'].includes(role))tabs.push(['mental-health','Mental health']);
  if(['astronaut','flight_surgeon','nutritionist'].includes(role))tabs.push(['nutrition-plans','Nutrition plans']);
  if(['astronaut','flight_surgeon','nurse'].includes(role))tabs.push(['nursing','Nursing care']);
  if(['mission_admin','astronaut','flight_surgeon'].includes(role))tabs.push(['requirements','Requirements']);
  if(role==='astronaut'||role==='flight_surgeon'&&physician)tabs.push(['allergies','Medical record · allergies']);
  return tabs;
}
export function initialMissionTab(role) {
  return {astronaut:'checklist',flight_surgeon:'checklist',psychologist:'mental-health',nutritionist:'nutrition-plans',nurse:'nursing'}[role] || 'operations';
}
