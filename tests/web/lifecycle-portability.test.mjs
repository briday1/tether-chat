import test from 'node:test';
import assert from 'node:assert/strict';
import {Model,emptyState} from '../../web/store.mjs';
import {exportData,importData,validateBackup} from '../../web/portable.mjs';
import {project,applyToState,makeChanges,materialize,mergeJournal,validateRecords} from '../../web/drive-sync-core.mjs';

const stamp='2026-11-03T14:00:00.000Z';
const tomorrow='2026-11-04T14:00:00.000Z';
const actor='device-lifecycle';

function example() {
  const model=new Model(emptyState(),()=>stamp,{maintenance:false});
  const task=model.create('Household paperwork','Bring the original',['Home']);
  const action=model.add(task.id,'action','Get the signature');
  const finished=model.add(task.id,'action','Find the form');
  model.updateAction(finished.id,{done:true});
  model.update(task.id,{recurrence:'weekly',next_occurrence:'2026-11-03',due_at:'2026-11-03'});
  model.addNote(action.id,'Use the current form');
  return {model,task: model.s.tasks[0],action,finished};
}

test('portable restore preserves snoozes, deferred occurrence and reversible completion',()=>{
  const {model,task,action,finished}=example();
  Object.assign(task,{snoozed_until:tomorrow,deferred_occurrence:'2026-11-03'});
  Object.assign(action,{done:true,completed_by_task:1,snoozed_until:tomorrow});
  const payload=exportData(model.s),restored=validateBackup(payload);
  assert.equal(restored.tasks[0].snoozed_until,tomorrow);
  assert.equal(restored.tasks[0].deferred_occurrence,'2026-11-03');
  assert.equal(restored.tasks[0].next_occurrence,'2026-11-03');
  assert.equal(restored.entries.find(row=>row.id===action.id).completed_by_task,true);
  assert.equal(restored.entries.find(row=>row.id===action.id).snoozed_until,tomorrow);
  assert.equal(restored.entries.find(row=>row.id===finished.id).completed_by_task,false);
  assert.equal(restored.notes[0].action_id,action.id);
  const target=emptyState();
  assert.equal(importData(target,payload).added.tasks,1);
  assert.equal(importData(target,payload).added.tasks,0);
});

test('task completion can be undone after backup restore or another Home device receives it',()=>{
  const {model,task,action,finished}=example();
  model.maintenance=true;
  model.update(task.id,{recurrence:null});
  model.completeTask(task.id);
  assert.ok(task.archived_at);
  const portable=validateBackup(exportData(model.s));
  const shared=emptyState();
  applyToState(shared,materialize([makeChanges([],{},project(model.s),actor,'operation-completed',stamp)]).records);
  for(const state of [portable,shared]){
    const reopened=new Model(state,()=>stamp).completeTask(task.id,false);
    assert.equal(reopened.state,'open');assert.equal(reopened.archived_at,null);
    assert.equal(reopened.entries.find(row=>row.id===action.id).done,false);
    assert.equal(!!reopened.entries.find(row=>row.id===finished.id).done,true);
    assert.ok(reopened.entries.every(row=>!row.completed_by_task));
  }
});

test('restored recurring deferral clears only its linked attention when completed',()=>{
  const {model,task}=example();
  model.deferTask(task.id,tomorrow);
  const restored=new Model(validateBackup(exportData(model.s)),()=>tomorrow);
  const completed=restored.complete(task.id,undefined,'2026-11-03');
  assert.equal(completed.revisit_at,null);
  assert.equal(completed.snoozed_until,null);
  assert.equal(completed.deferred_occurrence,null);
  assert.equal(completed.next_occurrence,'2026-11-10');
});

test('backup validation does not archive a partially restored settled task',()=>{
  const {model,task,action}=example();
  Object.assign(task,{recurrence:null,next_occurrence:null,recurrence_anchor:null,state:'settled',archived_at:null});
  const restored=validateBackup(exportData(model.s));
  assert.equal(restored.tasks[0].state,'settled');
  assert.equal(restored.tasks[0].archived_at,null);
  assert.equal(restored.entries.find(row=>row.id===action.id).done,false);
  // Even a fully completed old backup is restored faithfully; runtime maintenance
  // is responsible for its later archival, not the validation transaction.
  model.s.entries.forEach(row=>row.done=true);
  assert.equal(validateBackup(exportData(model.s)).tasks[0].archived_at,null);
});

test('old backups with absent lifecycle fields import repeatedly without false conflicts',()=>{
  const {model,task}=example();
  delete task.snoozed_until;delete task.deferred_occurrence;
  for(const entry of model.s.entries){delete entry.snoozed_until;delete entry.completed_by_task}
  const backup=exportData(model.s),restored=validateBackup(backup);
  assert.equal(restored.tasks[0].snoozed_until,null);
  assert.equal(restored.tasks[0].deferred_occurrence,null);
  assert.ok(restored.entries.every(row=>row.snoozed_until===null&&row.completed_by_task===false));
  assert.equal(importData(model.s,backup).added.tasks,0);
  assert.equal(importData(model.s,backup).added.entries,0);
});

test('malformed portable lifecycle metadata fails before changing existing data',()=>{
  const {model}=example();
  for(const change of [
    data=>data.tasks[0].snoozed_until='not-a-date',
    data=>data.tasks[0].deferred_occurrence='2026-02-30',
    data=>data.entries[0].snoozed_until='2026-11-04T09:00:00',
    data=>data.entries[0].completed_by_task='false',
    data=>data.entries[0].completed_by_task=null,
  ]){
    const backup=exportData(model.s);change(backup.data);
    const before=JSON.stringify(model.s);
    assert.throws(()=>importData(model.s,backup));
    assert.equal(JSON.stringify(model.s),before);
  }
});

test('Home sharing preserves lifecycle changes while concurrent task text merges',()=>{
  const {model,task,action}=example(),initial=project(model.s);
  const root=makeChanges([],{},initial,actor,'operation-root',stamp);
  const deferred=structuredClone(initial),edited=structuredClone(initial);
  Object.assign(deferred['task:'+task.id],{snoozed_until:tomorrow,deferred_occurrence:'2026-11-03'});
  Object.assign(deferred['entry:'+action.id],{snoozed_until:tomorrow,done:1,completed_by_task:1});
  edited['task:'+task.id].title='Household forms';
  const first=makeChanges([root],initial,deferred,actor,'operation-defer',stamp);
  const second=makeChanges([root],initial,edited,'device-partner','operation-title',stamp);
  const merged=materialize(mergeJournal([root,first],[root,second]));
  assert.equal(merged.conflicts.length,0);
  const state=emptyState();applyToState(state,merged.records);
  assert.equal(state.tasks[0].title,'Household forms');
  assert.equal(state.tasks[0].snoozed_until,tomorrow);
  assert.equal(state.tasks[0].deferred_occurrence,'2026-11-03');
  assert.equal(state.entries.find(row=>row.id===action.id).completed_by_task,1);
  assert.equal(state.entries.find(row=>row.id===action.id).snoozed_until,tomorrow);
  assert.equal(importData(state,exportData(state)).added.tasks,0);

  const cleared=structuredClone(merged.records);
  Object.assign(cleared['task:'+task.id],{snoozed_until:null,deferred_occurrence:null});
  Object.assign(cleared['entry:'+action.id],{snoozed_until:null,done:0,completed_by_task:0});
  const log=[root,first,second];
  const undo=makeChanges(log,merged.records,cleared,actor,'operation-reopen',stamp);
  const result=materialize([...log,undo]).records;
  assert.equal(result['task:'+task.id].snoozed_until,null);
  assert.equal(result['task:'+task.id].deferred_occurrence,null);
  assert.equal(result['entry:'+action.id].done,0);
  assert.equal(result['entry:'+action.id].completed_by_task,0);
});

test('legacy Home journals gain safe defaults without an upgrade-only sync operation',()=>{
  const {model,task,action}=example(),legacy=project(model.s);
  for(const [key,row] of Object.entries(legacy)){
    delete row.snoozed_until;
    if(key.startsWith('task:'))delete row.deferred_occurrence;
    if(key.startsWith('entry:'))delete row.completed_by_task;
  }
  validateRecords(legacy);
  const op=makeChanges([],{},legacy,actor,'operation-legacy',stamp);
  const shared=materialize([op]).records;
  assert.equal(shared['task:'+task.id].snoozed_until,null);
  assert.equal(shared['task:'+task.id].deferred_occurrence,null);
  assert.equal(shared['entry:'+action.id].completed_by_task,0);
  const state=emptyState();applyToState(state,legacy);
  assert.equal(makeChanges([op],legacy,project(state),actor,'operation-upgrade',stamp),null);
});

test('remote snoozes reset local delivery claims and do not share private context',()=>{
  const {model,task,action}=example();
  task.notified_for='old';task.action_prompt='private instruction';
  action.notified_for='old';model.s.settings={api_key:'private key'};
  model.s.messages=[{body:'private conversation'}];
  const shared=project(model.s);
  shared['task:'+task.id].snoozed_until=tomorrow;
  shared['entry:'+action.id].snoozed_until=tomorrow;
  assert.ok(!JSON.stringify(shared).includes('private'));
  applyToState(model.s,shared);
  assert.equal(model.s.tasks[0].notified_for,null);
  assert.equal(model.s.entries.find(row=>row.id===action.id).notified_for,null);
  assert.equal(model.s.tasks[0].action_prompt,'private instruction');
  assert.equal(model.s.settings.api_key,'private key');
  assert.equal(model.s.messages[0].body,'private conversation');
});

test('shared lifecycle fields remain type checked and restricted to the Home record schema',()=>{
  const {model,task,action}=example(),records=project(model.s);
  for(const [key,field,value] of [
    ['task:'+task.id,'snoozed_until','2026-11-04'],
    ['task:'+task.id,'deferred_occurrence','2026-11-04T09:00:00'],
    ['task:'+task.id,'deferred_occurrence','2026-02-30'],
    ['entry:'+action.id,'snoozed_until',false],
    ['entry:'+action.id,'completed_by_task','true'],
    ['entry:'+action.id,'completed_by_task',2],
    ['task:'+task.id,'assistant_context',{task_id:task.id}],
  ]){
    const bad=structuredClone(records);bad[key][field]=value;
    assert.throws(()=>validateRecords(bad));
  }
});
