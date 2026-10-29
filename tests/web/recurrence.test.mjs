import test from 'node:test';
import assert from 'node:assert/strict';
import {Model,emptyState} from '../../web/store.mjs';
import {occurrences,nextOccurrence,recurrenceValue} from '../../web/recurrence.mjs';
import {project,makeChanges,materialize,applyToState,validateRecords} from '../../web/drive-sync-core.mjs';
import {exportData,validateBackup,importData} from '../../web/portable.mjs';
function setup(fields,now='2026-01-01T00:00:00.000Z'){const model=new Model(emptyState(),()=>now);const task=model.create('Repeat');model.update(task.id,fields);return {model,id:task.id}}
const rows=(m,start,end)=>m.snapshot(start,end).days.flatMap(d=>d.tasks);
test('daily projections fill only requested range without materializing tasks or advancing current',()=>{
 const {model:m,id}=setup({recurrence:'daily',next_occurrence:'2000-01-01'});
 const result=rows(m,'2026-02-01','2026-02-28');assert.equal(result.length,28);assert.equal(m.s.tasks.length,1);assert.equal(m.get(id).next_occurrence,'2000-01-01');assert.ok(result.every(r=>r.id===id&&r.schedule_kinds.includes('recurrence')));
 assert.equal(rows(m,'2026-03-01','2026-03-31').length,31);assert.equal(rows(m,'1999-12-01','1999-12-31').length,0);
});
test('monthly anchor clamps February and restores original month day after completion',()=>{
 const {model:m,id}=setup({recurrence:'monthly',next_occurrence:'2026-01-31'},'2026-01-31T01:00:00Z');
 assert.deepEqual(rows(m,'2026-01-01','2026-04-30').map(r=>r.date),['2026-01-31','2026-02-28','2026-03-31','2026-04-30']);
 m.complete(id,undefined,'2026-01-31');assert.equal(m.get(id).next_occurrence,'2026-02-28');assert.equal(m.get(id).recurrence_anchor,'2026-01-31');
 m.update(id,{recurrence:'monthly',next_occurrence:'2026-02-28',summary:'Unchanged schedule'});assert.equal(m.get(id).recurrence_anchor,'2026-01-31');
 m.complete(id,undefined,'2026-02-28');assert.equal(m.get(id).next_occurrence,'2026-03-31');assert.equal(m.s.activity.length,2);
});
test('inclusive end bounds projections and completion exhaustion retains one task and history',()=>{
 const {model:m,id}=setup({recurrence:'weekly',next_occurrence:'2026-01-01',recurrence_end:'2026-01-15'},'2026-01-15T12:00:00Z');
 assert.deepEqual(rows(m,'2026-01-01','2026-02-28').map(r=>r.date),['2026-01-01','2026-01-08','2026-01-15']);m.complete(id);assert.equal(m.get(id).next_occurrence,null);assert.equal(m.get(id).recurrence,'weekly');assert.equal(rows(m,'2026-01-01','2026-02-28').length,0);assert.equal(m.s.activity.length,1);
});
test('schedule editing resets anchor, clear resets metadata, invalid ends are atomic',()=>{
 const {model:m,id}=setup({recurrence:'monthly',next_occurrence:'2026-01-31'});
 assert.throws(()=>m.update(id,{recurrence_end:'2026-01-30'}),/before/);assert.equal(m.get(id).recurrence_end,null);
 m.update(id,{next_occurrence:'2026-02-20'});assert.equal(m.get(id).recurrence_anchor,'2026-02-20');
 m.update(id,{recurrence:null});for(const key of ['next_occurrence','recurrence_anchor','recurrence_end','recurrence_timezone'])assert.equal(m.get(id)[key],null);
 assert.throws(()=>recurrenceValue('2026-02-30'),/Invalid/);
});
test('IANA daily repeats keep local wall time across DST, gap rolls forward and fold chooses earlier',()=>{
 const task={recurrence:'daily',next_occurrence:'2026-03-07T09:00:00-05:00',recurrence_timezone:'America/New_York'};
 assert.equal(nextOccurrence(task,'2026-03-07T15:00:00Z'),'2026-03-08T13:00:00.000Z');
 assert.equal(nextOccurrence({...task,next_occurrence:'2026-03-07T02:30:00-05:00'},'2026-03-07T08:00:00Z'),'2026-03-08T07:30:00.000Z');
 assert.equal(nextOccurrence({...task,next_occurrence:'2026-10-31T01:30:00-04:00'},'2026-10-31T08:00:00Z'),'2026-11-01T05:30:00.000Z');
 const legacy=nextOccurrence({...task,recurrence_timezone:null},'2026-03-07T15:00:00Z');assert.equal(legacy,'2026-03-08T09:00:00.000-05:00');
});
test('end uses schedule date rather than UTC and viewer day controls placement',()=>{
 const task={recurrence:'daily',next_occurrence:'2026-01-01T23:30:00-08:00',recurrence_timezone:'America/Los_Angeles',recurrence_end:'2026-01-02'};
 assert.equal(occurrences(task,'2026-01-01','2026-01-05').length,2);assert.equal(nextOccurrence(task,'2026-01-02T08:00:00Z'),'2026-01-03T07:30:00.000Z');
});
test('quarterly and leap yearly anchors restore day, settled and archived do not project',()=>{
 assert.deepEqual(occurrences({recurrence:'quarterly',next_occurrence:'2026-01-31'},'2026-01-01','2026-12-31').map(r=>r.date),['2026-01-31','2026-04-30','2026-07-31','2026-10-31']);
 assert.equal(nextOccurrence({recurrence:'yearly',next_occurrence:'2027-02-28',recurrence_anchor:'2024-02-29'},'2027-03-01'),'2028-02-29');
 for(const extra of [{state:'settled'},{archived_at:'2026-01-01T00:00:00Z'}])assert.equal(occurrences({recurrence:'daily',next_occurrence:'2026-01-01',...extra},'2026-01-01','2026-01-31').length,0);
});
test('portable and Drive round trips preserve recurrence; old shared journals remain readable',()=>{
 const {model:m,id}=setup({recurrence:'daily',next_occurrence:'2026-01-01',recurrence_end:'2026-02-01',recurrence_timezone:'America/New_York'});
 const restored=validateBackup(exportData(m.s));assert.equal(restored.tasks[0].recurrence_end,'2026-02-01');assert.equal(restored.tasks[0].next_occurrence,'2026-01-01');
 const records=project(m.s),op=makeChanges([],{},records,'actor-0001','operation-0001');const shared=materialize([op]).records,s=emptyState();applyToState(s,shared);assert.equal(s.tasks[0].recurrence_anchor,'2026-01-01');
 const old=structuredClone(op);old.changes=old.changes.filter(c=>!['recurrence_end','recurrence_anchor','recurrence_timezone'].includes(c.field));const legacy=materialize([old]).records;assert.equal(legacy['task:'+id].recurrence_end,null);validateRecords(legacy);
});
test('original fold instant survives projection; years below100 and year9999 stay bounded',()=>{
 const task={recurrence:'daily',next_occurrence:'2026-11-01T01:30:00-05:00',recurrence_timezone:'America/New_York'};
 assert.equal(occurrences(task,'2026-10-31','2026-11-02')[0].value,task.next_occurrence);
 assert.deepEqual(occurrences({recurrence:'monthly',next_occurrence:'0001-01-31'},'0001-01-01','0001-03-31').map(r=>r.value),['0001-01-31','0001-02-28','0001-03-31']);
 assert.equal(nextOccurrence({recurrence:'yearly',next_occurrence:'9999-12-31'},'9999-12-31'),null);
});
test('recurring due compares actual instants rather than offset text',()=>{
 const {model:m,id}=setup({recurrence:'daily',next_occurrence:'2026-01-01T01:00:00-08:00'},'2026-01-01T08:00:00Z');assert.equal(m.list()[0].recurring_due,false);
 m.clock=()=> '2026-01-01T10:00:00Z';assert.equal(m.list()[0].recurring_due,true);
 const before=JSON.stringify(m.s);m.snapshot('2026-01-01','2026-01-31');assert.equal(JSON.stringify(m.s),before);
});
test('legacy portable and journal without recurrence metadata import with safe defaults',()=>{
 const {model:m}=setup({recurrence:'daily',next_occurrence:'2026-01-01T09:00:00-05:00'}),backup=exportData(m.s);for(const field of ['recurrence_anchor','recurrence_end','recurrence_timezone'])delete backup.data.tasks[0][field];
 const restored=validateBackup(backup);assert.equal(restored.tasks[0].recurrence_end,null);assert.equal(restored.tasks[0].recurrence_anchor,'2026-01-01T09:00:00-05:00');
});

test('old task can import its own backup without a false metadata conflict',()=>{const {model:m,id}=setup({recurrence:'monthly',next_occurrence:'2026-01-31'});for(const field of ['recurrence_anchor','recurrence_end','recurrence_timezone'])delete m.s.tasks[0][field];assert.equal(importData(m.s,exportData(m.s)).added.tasks,0);const changed=exportData(m.s);changed.data.tasks[0].recurrence_end='2026-06-30';assert.throws(()=>importData(m.s,changed),/different version/)});
test('completion retries do not consume tomorrow and occurrence identity permits intentional early completion',()=>{
 const {model:m,id}=setup({recurrence:'daily',next_occurrence:'2026-01-31',recurrence_end:'2026-02-01',due_at:'2026-01-31T12:00:00Z',revisit_at:'2026-01-31T12:00:00Z'},'2026-01-31T13:00:00Z');
 const first=m.complete(id);assert.equal(first.next_occurrence,'2026-02-01');assert.equal(first.completion.occurrence_at,'2026-01-31');
 assert.equal(m.complete(id).next_occurrence,'2026-02-01');assert.equal(m.s.activity.length,1);
 assert.equal(m.complete(id,undefined,'2026-01-31').next_occurrence,'2026-02-01');assert.equal(m.s.activity.length,1);
 assert.equal(m.get(id).revisit_at,'2026-01-31T12:00:00.000Z');assert.equal(m.get(id).due_at,'2026-01-31T12:00:00.000Z');
 assert.equal(m.complete(id,undefined,'2026-02-01').next_occurrence,null);assert.equal(m.complete(id,undefined,'2026-02-01').next_occurrence,null);assert.equal(m.s.activity.length,2);
});
test('explicit future attention overrides an already-due recurrence',()=>{
 const {model:m,id}=setup({recurrence:'daily',next_occurrence:'2026-01-31',revisit_at:'2026-01-31T21:00:00Z'},'2026-01-31T18:00:00Z');
 assert.equal(m.list()[0].due,false);assert.equal(m.attention().items.length,0);
 m.update(id,{revisit_at:null});assert.equal(m.list()[0].due,true);
});
test('calendar deadlines preserve date-only identity across backup and sharing',()=>{
 const {model:m,id}=setup({due_at:'2026-01-31'},'2026-01-31T13:00:00Z');
 const a=m.add(id,'action','Deadline');m.updateAction(a.id,{due_at:'2026-02-01'});
 assert.equal(m.get(id).due_at,'2026-01-31');assert.equal(m.get(id).entries[0].due_at,'2026-02-01');
 assert.equal(m.list()[0].deadline_due,true);
 const imported=validateBackup(exportData(m.s));assert.equal(imported.tasks[0].due_at,'2026-01-31');
 const records=project(m.s);validateRecords(records);
});
test('date-only due flags respect local rollover on either side of UTC and DST',async()=>{
 const {execFileSync}=await import('node:child_process');
 for(const [TZ,stamp,today,tomorrow] of [['America/Los_Angeles','2026-11-01T06:30:00Z','2026-10-31','2026-11-01'],['Pacific/Kiritimati','2026-10-31T10:30:00Z','2026-11-01','2026-11-02']]){
  const script=`import assert from 'node:assert/strict';import {Model,emptyState} from './web/store.mjs';const m=new Model(emptyState(),()=>${JSON.stringify(stamp)});const t=m.create('Boundary');m.update(t.id,{recurrence:'daily',next_occurrence:${JSON.stringify(tomorrow)},due_at:${JSON.stringify(tomorrow)}});assert.equal(m.list()[0].due,false);assert.equal(m.list()[0].deadline_due,false);m.update(t.id,{next_occurrence:${JSON.stringify(today)},due_at:${JSON.stringify(today)}});assert.equal(m.list()[0].due,true);assert.equal(m.list()[0].deadline_due,true);`;
  execFileSync(process.execPath,['--input-type=module','-e',script],{cwd:new URL('../../',import.meta.url),env:{...process.env,TZ}});
 }
});
