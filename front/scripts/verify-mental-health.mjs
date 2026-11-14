import assert from 'node:assert/strict';
import {buildSync} from 'esbuild';
import {chromium} from 'playwright';

const bundle = role=>buildSync({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import MentalHealth from './src/MentalHealth.jsx';const request=async(path,options={})=>{const response=await fetch('http://mental.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});const data=await response.json();if(!response.ok)throw new Error(data.detail);return data;};createRoot(document.getElementById('root')).render(<MentalHealth request={request} mission={{id:1}} members={[{id:2,user_id:3,role:'astronaut'}]} names={()=>'Ada'} role="${role}" currentUserId={${role==='astronaut'?3:4}}/>);`,loader:'jsx',resolveDir:process.cwd()},bundle:true,write:false,format:'iife',loader:{'.css':'empty'}}).outputFiles[0].text;
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
try {
  const page=await browser.newPage();
  const data={today:'2026-11-14',timezone:'America/Bahia',check_ins:[],requests:[],sessions:[],sleep_observations:[],weeks:[{week_number:1,start:'2026-11-01',end:'2026-11-07',session_ids:[7]},{week_number:2,start:'2026-11-08',end:'2026-11-14',session_ids:[]}],days:[{date:'2026-11-13',check_in_id:null},{date:'2026-11-14',check_in_id:null}]};
  let checkInAttempts=0, sessionAttempts=0, requestCount=0;
  const payloads=[];
  await page.route('http://mental.test/**',async route=>{
    const path=new URL(route.request().url()).pathname, method=route.request().method();
    if(method==='PUT'&&path.includes('/check-ins/')){
      checkInAttempts++;payloads.push(route.request().postDataJSON());
      if(checkInAttempts===1)return route.fulfill({status:500,json:{detail:'Save failed. Please retry.'}});
      data.check_ins=[{id:1,check_in_date:'2026-11-14',created_at:'2026-11-14T10:00:00Z',updated_at:'2026-11-14T10:00:00Z',...payloads.at(-1)}];data.days[1].check_in_id=1;
      return route.fulfill({json:data.check_ins[0]});
    }
    if(method==='POST'&&path.endsWith('/requests')){requestCount++;data.requests=[{id:5,status:'pending',created_at:'2026-11-14T10:00:00Z'}];return route.fulfill({json:data.requests[0]});}
    if(method==='POST'&&path.endsWith('/sessions')){
      sessionAttempts++;payloads.push(route.request().postDataJSON());
      if(sessionAttempts===1)return route.fulfill({status:500,json:{detail:'Session save failed. Please retry.'}});
      data.sessions=[{id:8,psychologist_user_id:4,updated_by_user_id:4,updated_at:'2026-11-14T10:00:00Z',...payloads.at(-1)}];data.requests[0].status='fulfilled';data.weeks[1].session_ids=[8];return route.fulfill({json:data.sessions[0]});
    }
    if(path.endsWith('/astronauts'))return route.fulfill({json:[{member_id:2,user_id:3,pending_requests:data.requests.filter(item=>item.status==='pending'),weeks:data.weeks}]});
    return route.fulfill({json:data});
  });
  await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('astronaut')});
  await page.getByRole('heading',{name:'Daily check-in · 2026-11-14'}).waitFor();
  await page.locator('select[name="happiness_level"]').selectOption('4');
  await page.locator('select[name="satisfaction_level"]').selectOption('3');
  await page.getByLabel('Daily account (optional)').fill('Keep this daily account');
  await page.getByRole('button',{name:'Save check-in',exact:true}).click();
  await page.getByRole('alert').getByText('Save failed. Please retry.').waitFor();
  assert.equal(await page.getByLabel('Daily account (optional)').inputValue(),'Keep this daily account');
  await page.getByRole('button',{name:'Save check-in',exact:true}).click();
  await page.getByText('Check-in saved.',{exact:true}).waitFor();
  assert.equal(payloads.at(-1).sleep_quality,null);
  await page.getByRole('button',{name:'2026-11-13 No record'}).waitFor();
  await page.getByRole('button',{name:'Request a conversation',exact:true}).click();
  await page.getByRole('button',{name:'Conversation requested',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Conversation requested',exact:true}).isDisabled(),true);
  assert.equal(requestCount,1);
  await page.reload();await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('psychologist')});
  await page.getByRole('button',{name:/Ada 1 pending requests/}).click();
  await page.getByRole('button',{name:'Record conversation',exact:true}).click();
  await page.getByLabel('Session summary',{exact:true}).fill('Private conversation summary');
  await page.getByLabel('Private notes',{exact:true}).fill('Private psychologist note');
  await page.getByLabel('Agreed actions',{exact:true}).fill('Shared action');
  await page.getByLabel('Share agreed actions with the astronaut',{exact:true}).check();
  await page.getByLabel('Contact request',{exact:true}).selectOption('5');
  await page.getByRole('button',{name:'Save follow-up',exact:true}).click();
  await page.getByRole('alert').getByText('Session save failed. Please retry.').waitFor();
  assert.equal(await page.getByLabel('Private notes',{exact:true}).inputValue(),'Private psychologist note');
  await page.getByRole('button',{name:'Save follow-up',exact:true}).click();
  await page.getByText('Follow-up saved.',{exact:true}).waitFor();
  assert.equal(payloads.at(-1).share_agreed_actions,true);
  assert.equal(payloads.at(-1).share_next_follow_up,false);
  assert.equal(payloads.at(-1).contact_request_id,5);
  assert.equal(payloads.at(-1).review_period_start,'2026-11-08');
  assert.equal(data.requests[0].status,'fulfilled');
  await page.getByText('Week 2 · 2026-11-08 – 2026-11-14 · 1 conversation(s) recorded',{exact:true}).waitFor();
  console.log('Mental health: daily form, gaps, null optional fields, pending request, weekly follow-up, sharing and draft preservation passed.');
} finally {await browser.close();}
