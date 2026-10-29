import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const board=readFileSync(new URL('../../tether/board.html',import.meta.url),'utf8');
function editor(task){
 const controls=Object.fromEntries(['recurrence','occurrenceAllDay','nextOccurrence','recurrenceEnd','recurrenceZone'].map(id=>['#'+id,{value:'',checked:false,type:'',textContent:''}]));
 const ctx=vm.createContext({Date,Intl,console,$:selector=>controls[selector]});
 vm.runInContext(board.slice(board.indexOf('let recurrenceOriginal=null;'),board.indexOf("$('#occurrenceAllDay').onchange")),ctx);
 ctx.loadRecurrence(task);
 return {ctx,controls,changes:()=>JSON.parse(JSON.stringify(ctx.recurrenceChanges()))};
}
test('editor retains unchanged date-only and saved-zone schedules without resetting their anchor',()=>{
 for(const task of [{recurrence:'monthly',next_occurrence:'2026-01-31',recurrence_end:'2026-05-31'}, {recurrence:'weekly',next_occurrence:'2026-10-29T13:00:00Z',recurrence_timezone:'America/New_York'}]){
  const ui=editor(task);assert.deepEqual(ui.changes(),{recurrence:task.recurrence,recurrence_end:task.recurrence_end||null});
 }
 const ui=editor({recurrence:'daily',next_occurrence:'2026-10-29T13:00:00Z',recurrence_timezone:'America/New_York'});
 assert.equal(ui.controls['#nextOccurrence'].value,'2026-10-29T09:00');
 ui.controls['#nextOccurrence'].value='2026-11-02T09:00';
 assert.equal(ui.changes().next_occurrence,'2026-11-02T14:00:00.000Z');
 assert.equal(ui.changes().recurrence_timezone,'America/New_York');
});
test('editor handles timezone gaps forward and folds at the earlier instant',()=>{
 const {ctx}=editor({});
 assert.equal(ctx.recurrenceTimestamp('2026-03-08T02:30','America/New_York'),'2026-03-08T07:30:00.000Z');
 assert.equal(ctx.recurrenceTimestamp('2026-11-01T01:30','America/New_York'),'2026-11-01T05:30:00.000Z');
});
test('calendar occurrence timing omits unrelated task dates',()=>{
 const page=readFileSync(new URL('../../tether/snapshot.html',import.meta.url),'utf8');
 const ctx=vm.createContext({Date,dateOnly:d=>d.toISOString().slice(0,10),formatWhen:s=>s});
 vm.runInContext(page.slice(page.indexOf('function scheduleDay'),page.indexOf('function formatWhen')),ctx);
 assert.equal(ctx.timing({date:'2026-11-05',due_at:'2026-11-01',revisit_at:'2026-11-02',next_occurrence:'2026-10-29',occurrence_at:'2026-11-05'}),'Occurrence 2026-11-05');
 assert.ok(page.includes("detailSection('Schedule',timing(t))"));
});
test('shared recurrence controls are labeled and save guards duplicate submission',()=>{
 for(const [id,type] of [['recurrenceEnd','date'],['occurrenceAllDay','checkbox']])assert.match(board,new RegExp('type="'+type+'" id="'+id+'"'));
 assert.ok(board.includes('Repeat through (optional, inclusive)'));
 assert.ok(board.includes("form.setAttribute('aria-busy','true');save.disabled=true"));
 assert.ok(board.includes("if(current===taskId)await open(taskId)"));
 assert.ok(board.includes("finally{form.setAttribute('aria-busy','false');save.disabled=false}"));
});
test('completing a recurrence ignores double clicks and never reopens a different task',async()=>{
 const source=board.slice(board.indexOf('let completingOccurrence=false;'),board.indexOf("$('#note').onsubmit"));
 let resolvePost;const post=new Promise(resolve=>{resolvePost=resolve});const calls=[],opened=[],button={disabled:false,setAttribute(){}};
 const ctx=vm.createContext({current:'first',$:()=>button,api:async(...args)=>{calls.push(args);await post},load:async()=>{},open:async id=>opened.push(id),error:e=>{throw e}});
 vm.runInContext(source,ctx);
 const first=button.onclick();const second=button.onclick();
 assert.equal(button.disabled,true);assert.equal(calls.length,1);
 ctx.current='second';resolvePost();await Promise.all([first,second]);
 assert.deepEqual(opened,[]);assert.equal(calls[0][0],'/threads/first/complete-occurrence');
});
