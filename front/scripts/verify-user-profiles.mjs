import assert from 'node:assert/strict';
import {buildSync} from 'esbuild';
import {chromium} from 'playwright';

const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||'/usr/bin/google-chrome'});
const user={id:1,name:'Global admin',is_global_admin:true,is_active:true};
const bundle=(component,props)=>buildSync({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import Component from './src/${component}.jsx';const request=async(path,options={})=>{const response=await fetch('http://profiles.test'+path,{...options,body:options.body?JSON.stringify(options.body):undefined});const body=await response.json();if(!response.ok)throw new Error(body.detail);return body;};createRoot(document.getElementById('root')).render(<Component request={request} {...${JSON.stringify(props)}} names={id=>'User #'+id} onChanged={async()=>{}}/>);`,loader:'jsx',resolveDir:process.cwd()},bundle:true,write:false,format:'iife',loader:{'.css':'empty'}}).outputFiles[0].text;
try {
  const page=await browser.newPage();
  const payloads=[],records={nutrition:[],nursing:[]};let profileAttempts=0,careAttempts=0;
  await page.route('http://profiles.test/**',async route=>{
    const path=new URL(route.request().url()).pathname,method=route.request().method();
    if(path.endsWith('/access-audit'))return route.fulfill({json:{data:[],pagination:{has_next:false}}});
    if(path.endsWith('/profiles')){profileAttempts++;const body=route.request().postDataJSON();payloads.push(body);return route.fulfill(profileAttempts===1?{status:409,json:{detail:'Account changed. Please retry.'}}:{json:{...user,...body}});}
    if(path.endsWith('/nutrition-context'))return route.fulfill({json:{allergies:[],latest_blood_glucose:null}});
    const kind=path.includes('nutrition-plans')?'nutrition':'nursing';
    if(method==='POST'){
      careAttempts++;const body=route.request().postDataJSON();payloads.push(body);
      if(careAttempts===1)return route.fulfill({status:500,json:{detail:'Care save failed. Retry.'}});
      const record={id:careAttempts,author_user_id:kind==='nutrition'?4:5,updated_at:new Date().toISOString(),...body};records[kind].push(record);return route.fulfill({json:record});
    }
    return route.fulfill({json:records[kind]});
  });
  await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('UserAdministration',{users:[user]})});
  await page.getByRole('button',{name:'Manage profiles for Global admin'}).click();
  const dialog=page.getByRole('dialog');await dialog.getByLabel('Nurse',{exact:true}).check();
  await dialog.getByRole('button',{name:'Save profiles'}).click();
  await dialog.getByRole('alert').getByText('Account changed. Please retry.').waitFor();
  assert.equal(await dialog.getByLabel('Nurse',{exact:true}).isChecked(),true);
  await dialog.getByRole('button',{name:'Save profiles'}).click();await page.getByText('Account profiles updated.',{exact:true}).waitFor();assert.equal(payloads.at(-1).is_nurse,true);
  const props={mission:{id:1},members:[{id:2,user_id:3,role:'astronaut'}],currentUserId:5,role:'nurse',kind:'nursing'};
  await page.reload();await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('CareRecords',props)});
  await page.getByRole('button',{name:'Record nursing care',exact:true}).click();
  await page.getByLabel('Nursing observations',{exact:true}).fill('Preserve nursing observations');await page.getByLabel('Care provided',{exact:true}).fill('Sample collected');
  await page.getByRole('button',{name:'Save care record'}).click();await page.getByRole('alert').getByText('Care save failed. Retry.').waitFor();assert.equal(await page.getByLabel('Nursing observations',{exact:true}).inputValue(),'Preserve nursing observations');
  await page.getByRole('button',{name:'Save care record'}).click();await page.getByText('Care record saved.',{exact:true}).waitFor();
  await page.reload();await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('CareRecords',{...props,currentUserId:4,role:'nutritionist',kind:'nutrition'})});
  await page.getByRole('button',{name:'New nutrition plan',exact:true}).click();await page.getByLabel('Dietary guidance',{exact:true}).fill('Daily dietary guidance');
  await page.getByLabel('Energy target (kcal/day, optional)',{exact:true}).fill('2200');await page.getByRole('button',{name:'Save care record'}).click();await page.getByText('Care record saved.',{exact:true}).waitFor();assert.equal(payloads.at(-1).energy_target_kcal,2200);assert.equal(payloads.at(-1).hydration_target_ml,null);
  await page.reload();await page.setContent('<div id="root"></div>');await page.addScriptTag({content:bundle('CareRecords',{...props,currentUserId:3,role:'astronaut',kind:'nutrition'})});
  await page.getByText('Daily dietary guidance',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'New nutrition plan',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Correct record',exact:true}).count(),0);
  console.log('User profiles: administration, failed-save recovery, nursing, nutrition plans and astronaut read-only access passed.');
} finally {await browser.close();}
