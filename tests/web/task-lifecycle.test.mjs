import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyState,Model,isSnoozed} from '../../web/store.mjs';

function setup(stamp='2026-11-03T14:00:00Z') {
  const clock={value:stamp};
  return {m:new Model(emptyState(),()=>clock.value),clock};
}

test('whole task deferral hides overdue parent and children while retaining deadline facts',()=>{
  const {m,clock}=setup(), task=m.create('Prepare report');
  m.update(task.id,{due_at:'2026-11-02',revisit_at:'2026-11-03T13:59:00Z'});
  const action=m.add(task.id,'action','Collect notes');
  m.updateAction(action.id,{due_at:'2026-11-02',revisit_at:'2026-11-03T13:59:30Z'});
  const children=structuredClone(m.get(task.id).entries);
  assert.equal(m.attention().items.length,2);
  const deferred=m.deferTask(task.id,'2026-11-04T09:00:00-05:00');
  assert.equal(deferred.due_at,'2026-11-02');assert.deepEqual(deferred.entries,children);
  assert.ok(m.list()[0].deadline_due);assert.equal(m.list()[0].attention_due,false);
  assert.deepEqual(m.attention().items,[]);
  clock.value='2026-11-04T13:59:59Z';assert.deepEqual(m.attention().items,[]);
  clock.value='2026-11-04T14:00:00Z';
  assert.deepEqual(new Set(m.attention().items.map(i=>i.id)),new Set([task.id,action.id]));
});

test('individual action deferral leaves sibling and parent schedules independent',()=>{
  const {m}=setup(), task=m.create('Project'),first=m.add(task.id,'action','First'),second=m.add(task.id,'action','Second');
  for(const a of [first,second])m.updateAction(a.id,{due_at:'2026-11-02'});
  const before=structuredClone(m.get(task.id));
  m.deferAction(first.id,'2026-11-04T09:00:00-05:00');
  assert.deepEqual(m.attention().items.map(i=>i.id),[second.id]);
  assert.equal(m.get(task.id).revisit_at,before.revisit_at);assert.deepEqual(m.get(task.id).entries[1],before.entries[1]);
  assert.equal(m.action(first.id).due_at,'2026-11-02');
  m.deferAction(first.id,null);
  assert.deepEqual(new Set(m.attention().items.map(i=>i.id)),new Set([first.id,second.id]));
});

test('future reminder edits and capture followups suppress overdue attention',()=>{
  const {m}=setup(), task=m.create('Send form');
  m.update(task.id,{due_at:'2026-11-01',revisit_at:'2026-11-04T14:00:00Z'});
  assert.equal(m.get(task.id).snoozed_until,'2026-11-04T14:00:00.000Z');assert.deepEqual(m.attention().items,[]);
  m.deferTask(task.id,null);assert.equal(m.attention().items[0].id,task.id);
  const reused=m.capture({title:'Send form',existing_id:task.id,remind_at:'2026-11-04T14:00:00Z'});
  assert.equal(reused.reused,true);assert.ok(m.isSnoozed(reused));assert.equal(reused.due_at,'2026-11-01');
  assert.deepEqual(m.attention().items,[]);
  m.update(task.id,{revisit_at:null});
  const action=m.add(task.id,'action','Attachment');
  m.updateAction(action.id,{due_at:'2026-11-01',revisit_at:'2026-11-04T14:00:00Z'});
  assert.ok(!m.attention().items.some(i=>i.action_id===action.id));
});

test('legacy future reminders suppress even without snooze metadata',()=>{
  const {m}=setup(), task=m.create('Imported reminder');
  Object.assign(m.task(task.id),{due_at:'2026-11-02',revisit_at:'2026-11-04T14:00:00Z'});
  delete m.task(task.id).snoozed_until;
  assert.ok(m.isSnoozed(m.task(task.id)));assert.deepEqual(m.attention().items,[]);
  assert.equal(isSnoozed({snoozed_until:'broken'},'2026-11-03T14:00:00Z'),false);
});

for(const [current,until] of [
  ['2026-11-01T05:30:00Z','2026-11-01T01:15:00-05:00'],
  ['2026-12-31T18:59:59Z','2027-01-01T09:00:00+14:00'],
])test(`deferral expires at actual instant across offset/calendar boundary ${until}`,()=>{
  const {m,clock}=setup(current),task=m.create('Time boundary');m.update(task.id,{due_at:'2026-01-01'});
  m.deferTask(task.id,until);assert.deepEqual(m.attention().items,[]);
  clock.value=until;assert.equal(m.attention().items[0].id,task.id);
});

test('invalid, naive, date-only and already-past deferrals fail without writes',()=>{
  const {m}=setup(),task=m.create('Leave alone'),action=m.add(task.id,'action','Leave action alone');
  const before=structuredClone(m.s);
  for(const when of ['yesterday','2026-11-04','2026-11-04T09:00:00','2026-11-03T13:59:59Z','2026-11-03T14:00:00Z']) {
    assert.throws(()=>m.deferTask(task.id,when));assert.deepEqual(m.s,before);
    assert.throws(()=>m.deferAction(action.id,when));assert.deepEqual(m.s,before);
  }
});

test('complete and undo retain data and only undo children completed by whole-task checkbox',()=>{
  const {m}=setup(),task=m.create('One-time report'),earlier=m.add(task.id,'action','Already finished'),open=m.add(task.id,'action','Send report');
  m.updateAction(earlier.id,{done:true});m.addNote(open.id,'Reviewed with the team');m.record(task.id,'Draft prepared');
  m.update(task.id,{due_at:'2026-11-03',revisit_at:'2026-11-03T13:59:00Z'});
  const before=structuredClone(m.get(task.id)),completed=m.completeTask(task.id);
  assert.equal(completed.state,'settled');assert.ok(completed.archived_at);
  assert.ok(completed.entries.every(e=>e.done));assert.equal(m.action(earlier.id).completed_by_task,false);assert.equal(m.action(open.id).completed_by_task,true);
  assert.deepEqual(completed.activity,before.activity);assert.equal(completed.entries[1].notes[0].body,'Reviewed with the team');
  assert.deepEqual(m.board(),[]);assert.deepEqual(m.attention().items,[]);
  m.completeTask(task.id); // Retrying cannot erase the undo information.
  const reopened=m.completeTask(task.id,false);
  assert.equal(reopened.state,'open');assert.equal(reopened.archived_at,null);
  assert.equal(m.action(earlier.id).done,true);assert.equal(m.action(open.id).done,false);
  assert.equal(reopened.revisit_at,before.revisit_at);assert.equal(reopened.due_at,before.due_at);assert.deepEqual(reopened.activity,before.activity);
});

test('restoring archive reopens completed task and individual action undo restores visibility',()=>{
  const {m}=setup(),task=m.create('Restore me'),action=m.add(task.id,'action','Do it'),sibling=m.add(task.id,'action','Sibling');
  m.completeTask(task.id);const restored=m.update(task.id,{archived_at:null});
  assert.equal(restored.state,'open');assert.equal(restored.archived_at,null);assert.ok(restored.entries.every(e=>!e.done));
  assert.equal(m.list()[0].archived_at,null);
  m.completeTask(task.id);m.updateAction(action.id,{done:false});
  assert.equal(m.task(task.id).state,'open');assert.equal(m.task(task.id).archived_at,null);
  assert.equal(m.action(action.id).done,false);assert.equal(m.action(sibling.id).done,true);
});

test('last child completion does not infer ongoing subject completion',()=>{
  const {m}=setup(),task=m.create('Ongoing project'),action=m.add(task.id,'action','First milestone');
  m.updateAction(action.id,{done:true});assert.equal(m.task(task.id).state,'open');assert.equal(m.task(task.id).archived_at,null);
  m.update(task.id,{state:'settled'});assert.ok(m.task(task.id).archived_at);
});

test('legacy maintenance only archives settled nonrecurring tasks with no unfinished actions',()=>{
  const {m}=setup(),finished=m.create('Old finished'),blocked=m.create('Old settled with unfinished work'),repeated=m.create('Recurring commitment');
  const open=m.add(blocked.id,'action','Still open');m.update(repeated.id,{recurrence:'weekly',next_occurrence:'2026-11-03'});
  for(const task of m.s.tasks){task.state='settled';delete task.snoozed_until;delete task.deferred_occurrence;}
  for(const entry of m.s.entries){delete entry.snoozed_until;delete entry.completed_by_task;}
  m.list();assert.ok(m.task(finished.id).archived_at);assert.equal(m.task(blocked.id).archived_at,null);assert.equal(m.task(repeated.id).archived_at,null);
  m.updateAction(open.id,{done:true});assert.ok(m.task(blocked.id).archived_at);
  assert.equal(m.autoArchive().archived,0);
});

test('maintenance can be disabled while restoring an incomplete imported graph',()=>{
  const state=emptyState(),m=new Model(state,()=> '2026-11-03T14:00:00Z',{maintenance:false}),task=m.create('Imported settled subject');
  m.update(task.id,{state:'settled',archived_at:null});m.add(task.id,'action','Not finished');
  assert.equal(m.task(task.id).state,'settled');assert.equal(m.task(task.id).archived_at,null);
  assert.equal(m.list()[0].archived_at,null);
  assert.equal(new Model(state,()=> '2026-11-03T14:00:00Z').autoArchive().archived,0);
});

test('recurring deferral retains identity, only consumes its linked reminder, and cannot bulk complete',()=>{
  const {m,clock}=setup(),task=m.create('Daily review');m.update(task.id,{recurrence:'daily',next_occurrence:'2026-11-03',due_at:'2026-11-02'});
  const before=structuredClone(m.s);assert.throws(()=>m.completeTask(task.id));assert.deepEqual(m.s,before);
  const deferred=m.deferTask(task.id,'2026-11-04T14:00:00Z');
  assert.equal(deferred.next_occurrence,'2026-11-03');assert.equal(deferred.deferred_occurrence,'2026-11-03');assert.deepEqual(m.attention().items,[]);
  clock.value='2026-11-04T14:00:00Z';const completed=m.complete(task.id);
  assert.equal(completed.completion.completed,true);assert.equal(completed.next_occurrence,'2026-11-05');
  for(const key of ['revisit_at','snoozed_until','deferred_occurrence'])assert.equal(completed[key],null);
  assert.equal(completed.due_at,'2026-11-02');assert.equal(completed.state,'open');assert.equal(completed.archived_at,null);
  assert.equal(m.complete(task.id).completion.completed,false);
  m.deferTask(task.id,'2026-11-06T14:00:00Z');m.update(task.id,{revisit_at:'2026-11-07T14:00:00Z'});
  const early=m.complete(task.id,undefined,completed.next_occurrence);
  assert.equal(early.revisit_at,'2026-11-07T14:00:00.000Z');assert.equal(early.deferred_occurrence,null);
});

test('action text edits validate atomically and refresh parent revision',()=>{
  const {m,clock}=setup(),task=m.create('Parent'),action=m.add(task.id,'action','Old text'),before=structuredClone(m.s);
  for(const fields of [{body:' '},{done:'false'},{body:'Valid',revisit_at:'bad'}]){assert.throws(()=>m.updateAction(action.id,fields));assert.deepEqual(m.s,before);}
  clock.value='2026-11-03T14:01:00Z';assert.equal(m.updateAction(action.id,{body:'New text'}).body,'New text');assert.equal(m.task(task.id).updated_at,clock.value);
});
