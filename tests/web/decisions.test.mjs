import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {DEFAULT_PREFERENCES,resolveReminder,reminderIntent,taskKey} from '../../web/decisions.mjs';
import {emptyState,Model,snapshotRange} from '../../web/store.mjs';
import {exportData,importData} from '../../web/portable.mjs';
import {compatibleModels,modelOptions} from '../../web/provider.mjs';
import {requestLocation,locationRequests,beginSearch,finishSearch,saveLocation,parsePlaces} from '../../web/locations.mjs';
const local=(y,m,d,h=9,min=0)=>new Date(y,m-1,d,h,min).toISOString();
const now=new Date(2026,9,28,15);
const model=()=>new Model(emptyState(),()=>now.toISOString());
test('default calendar choices, preferences, and explicit times are deterministic',()=>{
 for(const [text,expected] of [['next day',local(2026,10,29)],['next week',local(2026,11,2)],['next month',local(2026,11,1)],['next year',local(2027,1,1)]])assert.equal(resolveReminder(text,{},now),expected);
 const p={week_start:0,morning_time:'10:30',night_time:'22:15'};
 assert.equal(resolveReminder('next week',p,now),local(2026,11,1,10,30));assert.equal(resolveReminder('tomorrow night',p,now),local(2026,10,29,22,15));
 assert.equal(resolveReminder('next week at 3pm',p,now),local(2026,11,1,15));
 assert.equal(reminderIntent('Remind me to call dentist next week at 3pm'),'next week at 3pm');assert.equal(reminderIntent('What happened next week?'),null);
 assert.equal(taskKey('Book my dental appt'),taskKey('Dentist appointment'));
 const dst=execFileSync(process.execPath,['--input-type=module','-e',"import {resolveReminder} from './web/decisions.mjs';process.stdout.write(resolveReminder('next week',{},new Date('2026-10-28T15:00:00Z')));"],{cwd:new URL('../../',import.meta.url),env:{...process.env,TZ:'America/New_York'}}).toString();
 assert.equal(dst,'2026-11-02T14:00:00.000Z');
});
test('assistant captures reuse suitable categories and tasks; preferences survive backup',()=>{
 const m=model();assert.deepEqual(m.preferences(),DEFAULT_PREFERENCES);m.create('Checkup','',['Medical']);
 const task=m.capture({title:'Make a dentist appointment',remind_at:'next week'});assert.deepEqual(task.categories,['Medical']);assert.equal(task.due_at,null);
 const again=m.capture({title:'Dentist appointment',remind_at:'next month'});assert.equal(again.id,task.id);assert.equal(again.reused,true);assert.equal(m.list().length,2);
 const old=m.create('Prescription pickup');assert.equal(m.capture({title:'Prescription pickup'}).id,old.id);assert.deepEqual(m.get(old.id).categories,['Medical']);
 assert.deepEqual(m.capture({title:'Repair garden fence',categories:['Unsorted']}).categories,['Home']);
 m.setPreferences({week_start:0,morning_time:'10:30',night_time:'22:15'});assert.throws(()=>m.setPreferences({week_start:4,morning_time:'25:00'}));assert.equal(m.preferences().week_start,0);
 const backup=exportData(m.s),target=emptyState();importData(target,backup);assert.deepEqual(new Model(target).preferences(),m.preferences());
 const custom=emptyState();new Model(custom).setPreferences({week_start:2});importData(custom,backup);assert.equal(new Model(custom).preferences().week_start,2);
});
test('snapshots include task, action and recurring reminders, combining same-day dates',()=>{
 const m=model(),task=m.create('Dentist','',['Health']);m.setPreferences({week_start:0});
 m.update(task.id,{due_at:local(2026,11,2,12),revisit_at:local(2026,11,2),recurrence:'monthly',next_occurrence:local(2026,11,3)});
 const a=m.add(task.id,'action','Call reception');m.updateAction(a.id,{revisit_at:local(2026,11,4)});
 const snapshot=m.snapshot('2026-11-01','2026-11-07'),rows=snapshot.days.flatMap(d=>d.tasks);assert.equal(rows.length,3);assert.equal(snapshot.week_start,0);
 assert.equal(rows[0].schedule_label,'Due · Reminder');assert.equal(rows[2].action_id,a.id);assert.equal(rows[2].title,'Call reception');assert.ok(rows[2].href.endsWith('/'+a.id));assert.deepEqual(rows[2].categories,['Health']);
 assert.deepEqual(snapshotRange('/snapshot next week',now,0),['2026-11-01','2026-11-07']);
 m.update(task.id,{archived_at:now.toISOString()});assert.equal(m.snapshot('2026-11-01','2026-11-07').insights.scheduled_due,0);
});
test('tool model catalog and explicit capability flags control discovery',()=>{
 const catalog=JSON.parse(readFileSync(new URL('../../tend/tool-models.json',import.meta.url))),base='https://api.openai.com/v1';
 assert.deepEqual(compatibleModels([{id:'gpt-4.1-mini'},{id:'gpt-6-luna'},{id:'gpt-6.1-sol'},{id:'gpt-6.1-terra'},{id:'text-embedding-3-small'},{id:'unknown'},{id:'gpt-4o',capabilities:{tool_calling:false}}],base,catalog),['gpt-4.1-mini','gpt-6-luna']);
 assert.deepEqual(modelOptions(base,'gpt-6-luna',catalog),{reasoning_effort:'none'});
 assert.deepEqual(compatibleModels([{id:'unknown'},{id:'tool-model',supported_parameters:['tools']},{id:'disabled',supports_tool_calling:false,supported_parameters:['tools']}],'https://provider.test/v1',catalog),['tool-model']);
});
test('address confirmation, result selection and saving are independent of the model',()=>{
 const m=model(),task=m.create('Dentist'),request=requestLocation(m,{id:task.id,query:'Example Dental London'});assert.equal(request.confirmation_required,true);assert.equal(request.status,'pending');
 const claim=beginSearch(m,request.id,'Example Dental London');
 const results=parsePlaces({features:[{properties:{name:'Example Dental',street:'High Street',housenumber:'12',city:'London',osm_id:123},geometry:{coordinates:[-0.12,51.5]}}]});
 finishSearch(m,request.id,claim.token,results);assert.throws(()=>saveLocation(m,request.id,'invented-result'));
 const saved=saveLocation(m,request.id,results[0].id);assert.equal(saveLocation(m,request.id,results[0].id).entry.id,saved.entry.id);assert.equal(m.get(task.id).entries.length,1);assert.ok(saved.entry.body.includes('Google Maps'));assert.ok(saved.entry.body.includes('12 High Street'));
 assert.equal(locationRequests(m)[0].status,'saved');
});
