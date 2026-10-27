import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyState,Model,categories,advance,snapshotRange,day} from '../../web/store.mjs';
import {exportData,importData,validateBackup} from '../../web/portable.mjs';
import {renderMarkdown} from '../../web/render.mjs';

const clock=()=> '2026-10-27T12:00:00.000Z';
function model(){return new Model(emptyState(),clock)}
test('categories share one task; action edits and notes remain scoped',()=>{
  const m=model(),task=m.create('Release','Details',['Work','Personal','work','Unsorted']);
  assert.deepEqual(task.categories,['Work','Personal']);assert.equal(m.board().length,2);assert.equal(m.list().length,1);
  const first=m.add(task.id,'action','Check package'),second=m.add(task.id,'action','Write notes');
  m.updateAction(first.id,{done:true,due_at:'2026-10-28',revisit_at:clock()});
  const note=m.addNote(first.id,'Test passed','note-first-001');
  assert.equal(m.addNote(first.id,'Test passed',note.id).id,note.id);
  assert.throws(()=>m.addNote(second.id,'Other text',note.id));
  assert.throws(()=>m.editNote(second.id,note.id,'Wrong scope'));
  assert.throws(()=>m.deleteNote(second.id,note.id));
  const detail=m.get(task.id);
  assert.equal(detail.due_at,null);assert.equal(detail.revisit_at,null);
  assert.equal(detail.entries[1].done,false);assert.equal(detail.entries[1].due_at,null);
  assert.deepEqual(detail.entries[1].notes,[]);assert.equal(detail.entries[0].notes.length,1);
  assert.equal(m.list('Test passed')[0].id,task.id);
  m.setCategories(task.id,['Household'],'add');m.setCategories(task.id,['work'],'remove');
  assert.deepEqual(m.get(task.id).categories,['Personal','Household']);
});
test('attention is action-specific, and archive/restore retains data',()=>{
  const m=model(),task=m.create('Paperwork','Context',['Admin']),a=m.add(task.id,'action','Return form');
  m.addNote(a.id,'Waiting for signature');m.updateAction(a.id,{revisit_at:'2026-10-26T09:00:00Z'});
  const attention=m.attention();assert.equal(attention.items[0].action_id,a.id);assert.equal(attention.items[0].task_id,task.id);
  m.update(task.id,{archived_at:clock()});assert.equal(m.attention().items.length,0);assert.equal(m.board().length,0);
  m.update(task.id,{archived_at:null});assert.equal(m.get(task.id).entries[0].notes.length,1);
  assert.equal(m.attention().items.length,1);assert.equal(m.get(task.id).entries[0].done,false);
});
test('recurrence clamps month ends and records one milestone on one task',()=>{
  assert.equal(advance('2026-01-31T09:00:00Z','monthly'),'2026-02-28T09:00:00.000Z');
  assert.equal(advance('2028-02-29T09:00:00Z','yearly'),'2029-02-28T09:00:00.000Z');
  const m=model(),task=m.create('Weekly review');m.update(task.id,{recurrence:'weekly',next_occurrence:'2026-10-01T09:00:00Z'});
  const completed=m.complete(task.id);assert.ok(completed.next_occurrence>clock());assert.equal(m.s.tasks.length,1);
  assert.equal(m.s.activity.length,1);assert.equal(m.s.activity[0].kind,'milestone');
});
test('reports use UTC Monday boundaries, exclusive ends, and all category memberships',()=>{
  const m=model(),task=m.create('Build','',['Work','Software']);
  m.record(task.id,'Sunday','progress','2026-10-25T23:59:59Z');
  m.record(task.id,'Monday','progress','2026-10-26T00:00:00Z');
  m.record(task.id,'Next Monday','progress','2026-11-02T00:00:00Z');
  const report=m.report('week',clock());assert.equal(report.count,1);assert.equal(report.events[0].body,'Monday');
  const scheduled=m.create('Report');m.update(scheduled.id,{due_action:'activity_report',action_config:{period:'week',category:'Software'}});
  assert.equal(m.dueReport(scheduled.id,'2026-11-02T00:00:00Z').count,1);
});
test('snapshots count multi-category tasks once, and retain archived historical activity',()=>{
  const m=model(),task=m.create('Release','',['Work','Software']);m.update(task.id,{due_at:'2026-10-27'});
  m.record(task.id,'Built release','progress',clock());
  const snapshot=m.snapshot('2026-10-26','2026-11-01','Software');
  assert.equal(snapshot.days.length,7);assert.equal(snapshot.insights.scheduled_due,1);assert.equal(snapshot.insights.activity_events,1);
  assert.deepEqual(snapshot.insights.categories,{Work:1,Software:1});
  m.update(task.id,{archived_at:clock()});const archived=m.snapshot('2026-10-26','2026-11-01');
  assert.equal(archived.insights.scheduled_due,0);assert.equal(archived.insights.activity_events,1);
  assert.throws(()=>m.snapshot('2026-11-01','2026-10-26'));assert.throws(()=>day('2026-02-31'));
});
test('snapshot commands handle next/last periods without any AI provider',()=>{
  const date=new Date('2026-10-27T12:00:00Z');
  assert.deepEqual(snapshotRange('/snapshot next week',date),['2026-11-02','2026-11-08']);
  assert.deepEqual(snapshotRange('give me my last month snapshot',date),['2026-09-01','2026-09-30']);
  assert.deepEqual(snapshotRange('/snapshot tomorrow',date),['2026-10-28','2026-10-28']);
  assert.deepEqual(snapshotRange('/snapshot 2026-10-27 to 2026-10-29',date),['2026-10-27','2026-10-29']);
  assert.equal(snapshotRange('Hello',date),null);assert.throws(()=>snapshotRange('/snapshot next 999 days',date));
});
test('portable backups round-trip relationships and notes without credentials or jobs',()=>{
  const m=model(),task=m.create('Task','',['Work']),other=m.create('Related');
  const action=m.add(task.id,'action','Do it');m.addNote(action.id,'A detail');m.link(task.id,other.id);m.record(task.id,'Update');
  m.s.messages.push({id:'message-001',role:'user',body:'Hello',created_at:clock()});
  m.s.settings={base_url:'https://secret.test',encrypted_key:{ciphertext:'secret-key'}};
  m.s.jobs=[{id:'not-replayed',status:'running'}];
  const backup=exportData(m.s);assert.ok(!JSON.stringify(backup).includes('secret'));assert.ok(!JSON.stringify(backup).includes('not-replayed'));
  const target=emptyState();importData(target,backup);assert.equal(target.tasks.length,2);
  assert.equal(new Model(target).get(task.id).entries[0].notes.length,1);assert.equal(target.jobs.length,0);
  assert.equal(new Model(target).get(task.id).related[0].id,other.id);
  assert.equal(importData(target,backup).added.tasks,0);
  const malformed=structuredClone(backup);malformed.data.notes[0].action_id='missing';
  assert.throws(()=>validateBackup(malformed));
  const conflicting=structuredClone(backup);conflicting.data.tasks[0].title='Changed';const before=JSON.stringify(target);
  assert.throws(()=>importData(target,conflicting));assert.equal(JSON.stringify(target),before);
});
test('provider and stored text cannot inject HTML; internal links honor Pages base path',()=>{
  const rendered=renderMarkdown('<script>alert(1)</script> [Task](/board#task/abc) [bad](javascript:alert)\n\n**Hello**',{base:'/tether-chat/'});
  assert.ok(!rendered.includes('<script>'));assert.ok(!rendered.includes('href="javascript:'));
  assert.ok(rendered.includes('href="/tether-chat/board.html#task/abc"'));assert.ok(rendered.includes('<strong>Hello</strong>'));
});
