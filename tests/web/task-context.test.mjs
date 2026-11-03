import test from 'node:test';
import assert from 'node:assert/strict';
import {Model,emptyState,copy} from '../../web/store.mjs';
import {buildTaskContext,deferIntent,searchHistory} from '../../web/task-context.mjs';
import {createRuntime} from '../../web/runtime.mjs';

class MemoryDB{
  state=emptyState();
  async read(fn){return copy(fn(new Model(this.state).s))}
  async write(fn){const next=copy(this.state),result=fn(next);this.state=next;return copy(result)}
}
class Locks{busy=false;async request(name,options,fn){if(this.busy)return fn(null);this.busy=true;try{return await fn({name})}finally{this.busy=false}}}
const config={base:'/tether/',origin:'https://tether.test',system:'Use saved tools.',tools:['get_context','get_action','search_history','defer_action'].map(name=>({type:'function',function:{name,parameters:{type:'object',properties:{}}}}))};
async function setup(t,network=()=>{throw Error('Unexpected provider request')}){
  const db=new MemoryDB(),runtime=await createRuntime({config,db,network,locks:new Locks(),session:{getItem:()=>null,setItem(){},removeItem(){}}});
  t.after(()=>runtime.close());
  const api=async(path,method='GET',body)=>{const response=await runtime.fetch(config.origin+config.base+'api'+path,{method,body:body===undefined?undefined:JSON.stringify(body)});return {status:response.status,data:await response.json()}};
  const task=(await api('/threads','POST',{title:'Report'})).data;
  const actions=[];for(const body of ['Review figures','Send appendix']){
    const action=(await api(`/threads/${task.id}/entries`,'POST',{kind:'action',body})).data;actions.push(action);
    await api(`/actions/${action.id}`,'PATCH',{due_at:'2020-01-01',revisit_at:'2020-01-01T09:00:00Z'});
  }
  await api(`/threads/${task.id}`,'PATCH',{due_at:'2020-01-01'});
  return {db,runtime,api,task,actions};
}
async function waitFor(check){for(let i=0;i<200;i++){if(check())return;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out')}

test('attention click then tomorrow reply defers only its selected action without AI',async t=>{
  const {api,db,task,actions:[selected,sibling]}=await setup(t);
  await api('/chat/jobs','POST',{request_id:'attention-focus-001',attention:{task_id:task.id,action_id:selected.id}});
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  const before=copy(db.state.entries.find(e=>e.id===sibling.id));
  const body={request_id:'tomorrow-focus-002',text:"Let's do that tomorrow",task_context:[task.id],action_context:selected.id};
  assert.equal((await api('/chat/preflight','POST',body)).status,200);
  assert.equal((await api('/chat/jobs','POST',body)).status,202);
  await waitFor(()=>db.state.jobs[1]?.status==='done');
  assert.deepEqual(db.state.jobs[1].result.actions,['defer_action']);
  assert.equal(db.state.jobs[1].changes_saved,true);
  const items=(await api('/attention')).data.items;
  assert.ok(!items.some(i=>i.id===selected.id));assert.ok(items.some(i=>i.id===sibling.id));
  assert.deepEqual(db.state.entries.find(e=>e.id===sibling.id),before);
  assert.equal(db.state.tasks[0].due_at,'2020-01-01');
  assert.equal(db.state.entries.find(e=>e.id===selected.id).due_at,'2020-01-01');
  assert.equal((await api('/chat/jobs','POST',body)).status,202);assert.equal(db.state.jobs.length,2);
  assert.equal((await api('/chat/jobs','POST',{...body,action_context:sibling.id})).status,422);
});

test('task defer, complete and undo endpoints agree with Attention and Archive',async t=>{
  const {api,task,actions}=await setup(t);
  assert.equal((await api(`/threads/${task.id}/defer`,'POST',{when:'tomorrow'})).status,200);
  assert.equal((await api('/attention')).data.items.length,0);
  const complete=await api(`/threads/${task.id}/complete`,'POST',{done:true});
  assert.ok(complete.data.archived_at);assert.equal((await api('/archived')).data.length,1);
  const restored=await api(`/threads/${task.id}/complete`,'POST',{done:false});
  assert.equal(restored.data.archived_at,null);assert.ok(restored.data.entries.every(e=>!e.done));
  await api(`/threads/${task.id}/defer`,'POST',{when:null});
  assert.ok((await api('/attention')).data.items.some(i=>i.task_id===task.id));
  assert.equal(restored.data.entries.length,actions.length);
});

test('action context rejects cross-task IDs before saving any request',async t=>{
  const {api,db,actions}=await setup(t),other=(await api('/threads','POST',{title:'Other'})).data;
  const response=await api('/chat/jobs','POST',{request_id:'cross-task-context',text:"Let's do that tomorrow",task_context:[other.id],action_context:actions[0].id});
  assert.equal(response.status,422);assert.equal(db.state.jobs.length,0);
});

test('rich context retains older unfinished action notes despite many later notes',()=>{
  const m=new Model(emptyState()),task=m.create('Task'),action=m.add(task.id,'action','Old open action');
  m.addNote(action.id,'Keep the agreed figures');for(let n=0;n<30;n++)m.add(task.id,'thought','New note '+n);
  const context=buildTaskContext(m,[task.id],action.id);
  assert.equal(context.focused_action.notes[0].body,'Keep the agreed figures');
  assert.ok(context.focused_task.actions.some(a=>a.id===action.id));
  assert.equal(context.focused_task.recent_notes.length,5);
  const cleared=buildTaskContext(m,[]);assert.equal(cleared.focused_task,null);assert.equal(cleared.focused_action,null);
});

test('local defer parser excludes hypothetical, compound and deadline requests',()=>{
  for(const text of ['If I say "let\'s do that tomorrow", what happens?','Should we do that tomorrow?','Move its deadline to tomorrow',"Let's do that tomorrow or next week","Let's do that tomorrow and send it now"])
    assert.equal(deferIntent(text),null,text);
  assert.equal(deferIntent("Let's do that tomorrow"),'tomorrow');
  assert.equal(deferIntent('Please postpone it until next week.'),'next week');
});

test('history search is bounded literal data and exposes more matches',()=>{
  const s=emptyState();s.messages=[{id:'1',role:'user',body:'100% complete'},{id:'2',role:'user',body:'100 percent complete'},{id:'3',role:'user',body:'100% reviewed'}];
  const result=searchHistory(s,'100%',1);assert.equal(result.has_more,true);assert.equal(result.messages[0].body,'100% reviewed');
  assert.equal(searchHistory(s,'percent').messages.length,1);assert.throws(()=>searchHistory(s,'a'));
});

test('expired deferral sends one nudge instead of repeating for its old deadline',async t=>{
  const original=globalThis.Notification,shown=[];
  globalThis.Notification=class {static permission='granted';constructor(title){shown.push(title)}};
  t.after(()=>{if(original===undefined)delete globalThis.Notification;else globalThis.Notification=original});
  const {db,runtime,actions:[selected,sibling]}=await setup(t);
  db.state.tasks[0].due_at=null;
  db.state.entries.find(e=>e.id===sibling.id).done=true;
  const action=db.state.entries.find(e=>e.id===selected.id),expired=new Date(Date.now()-1000).toISOString();
  Object.assign(action,{revisit_at:expired,snoozed_until:expired});
  await runtime.notifications();await runtime.notifications();
  assert.deepEqual(shown,[selected.body]);
});
