import test from 'node:test';
import assert from 'node:assert/strict';
import {accountProfiles, initialMissionTab, missionRoles, missionTabs, profileLabel} from '../src/user-profiles.js';

test('all eight account profiles have distinct labels',()=>{
  assert.equal(accountProfiles.length,8);
  assert.equal(Object.keys(missionRoles).length,7);
  assert.equal(profileLabel({is_physician:true,is_mission_admin:true}),'Physician · Mission administrator');
});

test('observer receives operational tabs without individual care records',()=>{
  assert.deepEqual(missionTabs('observer').map(([id])=>id),['operations','members']);
  assert.equal(initialMissionTab('observer'),'operations');
});

test('professional workspaces expose the appropriate care modules',()=>{
  const nurse=missionTabs('nurse').map(([id])=>id),nutritionist=missionTabs('nutritionist').map(([id])=>id),admin=missionTabs('mission_admin').map(([id])=>id);
  assert(nurse.includes('nursing'));
  assert(!nurse.includes('mental-health')&&!nurse.includes('nutrition-plans'));
  assert(nutritionist.includes('nutrition-plans'));
  assert(!nutritionist.includes('nursing')&&!nutritionist.includes('mental-health'));
  assert(!admin.includes('nursing')&&!admin.includes('mental-health')&&!admin.includes('checklist'));
  assert.equal(initialMissionTab('nurse'),'nursing');
  assert.equal(initialMissionTab('nutritionist'),'nutrition-plans');
});
