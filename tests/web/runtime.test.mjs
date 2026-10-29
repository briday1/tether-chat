import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyState,Model,copy} from '../../web/store.mjs';
import {createRuntime} from '../../web/runtime.mjs';

class MemoryDB {
  constructor(){this.state=emptyState()}
  async read(fn){return copy(fn(new Model(this.state).s))}
  async write(fn){const candidate=copy(this.state),result=fn(candidate);this.state=candidate;return copy(result)}
}
class Locks {
  busy=false;
  async request(name,options,fn){if(this.busy)return fn(null);this.busy=true;try{return await fn({name})}finally{this.busy=false}}
}
const config={base:'/tether-chat/',origin:'https://tether.test',version:'2026.7',system:'Use tools to save changes.',tools:[
  {type:'function',function:{name:'capture',parameters:{type:'object',required:['title'],properties:{title:{type:'string'}}}}}
]};
const provider=message=>Response.json({choices:[{message}]});
async function setup(t,network,db=new MemoryDB(),locks=new Locks(),options={}){
  const values=new Map(),session={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const runtime=await createRuntime({config,db,locks,session,network:network||(()=>{throw Error('Unexpected provider request')}),...options});t.after(()=>runtime.close());
  const api=async(path,method='GET',body)=>{
    const response=await runtime.fetch(config.origin+config.base+'api'+path,{method,body:body===undefined?undefined:JSON.stringify(body)});
    return {status:response.status,data:await response.json()};
  };
  return {runtime,api,db,session};
}
async function waitFor(check){for(let i=0;i<200;i++){const result=await check();if(result)return result;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out waiting for queue')}
async function save(api,key='test-user-key'){return api('/settings','POST',{base_url:'https://provider.test/v1',model:'tool-model',api_key:key,remember:false})}
test('long notes are preserved and oversize rejection keeps previous messages',async t=>{
  const {api,db}=await setup(t,()=>provider({content:'Notes received.'}));
  await save(api);
  const text='x'.repeat(50000);
  assert.equal((await api('/chat/jobs','POST',{request_id:'long-notes-request',text})).status,202);
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  assert.equal(db.state.messages[0].body,text);
  const before=copy(db.state.messages);
  assert.equal((await api('/chat/jobs','POST',{request_id:'oversize-request',text:text+'x'})).status,422);
  assert.deepEqual(db.state.messages,before);
});
test('local commands run without a key and submissions are idempotent',async t=>{
  const {api,db}=await setup(t);const body={request_id:'request-local-001',text:'/brief'};
  const first=await api('/chat/jobs','POST',body),repeat=await api('/chat/jobs','POST',body);
  assert.equal(first.status,202);assert.equal(first.data.id,repeat.data.id);
  await waitFor(()=>db.state.jobs[0]?.status==='done');assert.equal(db.state.messages.length,2);
  const changed=await api('/chat/jobs','POST',{...body,text:'Different'});assert.equal(changed.status,422);
  assert.equal(db.state.messages.length,2);const state=await api('/chat/state');assert.ok(state.data.messages[1].html.includes('Daily brief'));
});
test('populated local rollups render current actions and schedules without a provider',async t=>{
  const {api,db}=await setup(t);
  const task=(await api('/threads','POST',{title:'Review [A] | draft',summary:'Keep the supporting context.'})).data;
  await api('/threads/'+task.id+'/entries','POST',{kind:'action',body:'Check the attachment'});
  await api('/threads/'+task.id,'PATCH',{state:'waiting',due_at:'2020-01-01',revisit_at:'2020-01-02T12:00:00Z'});
  const archived=(await api('/threads','POST',{title:'Archived reference'})).data;
  await api('/threads/'+archived.id+'/archive','POST',{});
  await api('/chat/jobs','POST',{request_id:'note-rollup-001',text:'/brief'});
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  const answer=(await api('/chat/state')).data.messages.at(-1).html;
  assert.ok(answer.includes('<table>')&&answer.includes('Check the attachment')&&answer.includes('Keep the supporting context.'));
  assert.ok(answer.includes('Due 2020-01-01; Bring to attention 2020-01-02; Waiting'));
  assert.equal((answer.match(/<a /g)||[]).length,1);
  await api('/chat/jobs','POST',{request_id:'note-rollup-002',text:'/recent'});
  await waitFor(()=>db.state.jobs[1]?.status==='done');
  assert.ok(!db.state.messages.at(-1).body.includes(archived.id));
});
test('queue serializes calls and excludes later queued messages from earlier context',async t=>{
  const requests=[];let release;const gate=new Promise(resolve=>release=resolve);
  const {api,db}=await setup(t,async(url,options)=>{
    requests.push(JSON.parse(options.body));if(requests.length===1)await gate;
    return provider({role:'assistant',content:requests.length===1?'First answer':'Second answer'});
  });await save(api);
  await api('/chat/jobs','POST',{request_id:'request-first-001',text:'First message'});
  await waitFor(()=>requests.length===1);
  await api('/chat/jobs','POST',{request_id:'request-second-001',text:'Second message'});
  assert.equal(requests.length,1);assert.ok(!JSON.stringify(requests[0].messages).includes('Second message'));
  release();await waitFor(()=>db.state.jobs.every(j=>j.status==='done'));
  assert.equal(requests.length,2);assert.ok(JSON.stringify(requests[1].messages).includes('First answer'));
  assert.equal(db.state.messages.filter(m=>m.role==='assistant').length,2);
});
test('identical model tool calls mutate once, and keys stay out of backups',async t=>{
  let count=0;const {api,db}=await setup(t,async()=>{
    count++;return count===1?provider({role:'assistant',content:null,tool_calls:[
      {id:'tool-a',type:'function',function:{name:'capture',arguments:'{"title":"New task"}'}},
      {id:'tool-b',type:'function',function:{name:'capture',arguments:'{"title":"New task"}'}}
    ]}):provider({role:'assistant',content:'Saved the task.'});
  });await save(api,'secret-user-key');await api('/chat/jobs','POST',{request_id:'request-tools-001',text:'Remember a task'});
  await waitFor(()=>db.state.jobs[0]?.status==='done');assert.equal(db.state.tasks.length,1);
  assert.ok(!JSON.stringify((await api('/backup')).data).includes('secret-user-key'));
  assert.ok(!JSON.stringify(db.state.settings).includes('secret-user-key'));
});
test('encrypted saved keys unlock explicitly and remain pinned to their provider',async t=>{
  const {api,db,session}=await setup(t,async()=>provider({role:'assistant',content:'OK'}));
  const saved=await api('/settings','POST',{base_url:'https://provider.test/v1',model:'test',api_key:'secret-user-key',remember:true,passphrase:'unlock-passphrase'});
  assert.equal(saved.status,200);assert.ok(db.state.settings.encrypted_key.ciphertext);
  assert.ok(!JSON.stringify(db.state.settings).includes('secret-user-key'));
  await api('/settings/lock','POST',{});assert.equal((await api('/settings')).data.locked,true);
  assert.equal((await api('/settings/unlock','POST',{passphrase:'wrong-passphrase'})).status,422);
  assert.equal((await api('/settings/unlock','POST',{passphrase:'unlock-passphrase'})).status,200);
  assert.equal((await api('/settings/test','POST',{})).status,200);
  const previous=copy(db.state.settings);
  const changed=await api('/settings','POST',{base_url:'https://another-provider.test/v1',model:'test',remember:false});
  assert.equal(changed.status,422);assert.match(changed.data.detail,/Re-enter your API key/);
  assert.deepEqual(db.state.settings,previous);assert.equal((await api('/settings')).data.has_key,true);
  await api('/settings','POST',{base_url:'https://another-provider.test/v1',model:'test',api_key:'new-provider-key',remember:false});
  assert.equal((await api('/settings')).data.has_key,true);
  assert.ok(!session.getItem('tether-chat-web-key:'+config.base+':home').includes('secret-user-key'));
});
test('missing keys are caught before chat and a blank save cannot claim success',async t=>{
  const {api,db}=await setup(t);
  assert.equal((await api('/settings','POST',{base_url:'https://api.openai.com/v1',model:'test',remember:false})).status,422);
  assert.deepEqual(db.state.settings,{});
  assert.equal((await api('/chat/preflight','POST',{text:'Remember this task'})).status,401);
  assert.equal(db.state.jobs.length,0);assert.equal(db.state.messages.length,0);
  assert.equal((await api('/chat/preflight','POST',{text:'/brief'})).status,200);
  assert.equal((await api('/chat/preflight','POST',{text:'calendar view this week'})).status,200);
});
test('encrypted connections survive model edits and reopening without losing the saved key',async t=>{
  const network=async(url,options)=>{
    assert.equal(url,'https://provider.test/v1/chat/completions');assert.equal(options.headers.Authorization,'Bearer retained-key');
    return provider({role:'assistant',content:'OK'});
  };
  const first=await setup(t,network);
  await first.api('/settings','POST',{base_url:'https://provider.test/v1',model:'first-model',api_key:'retained-key',remember:true,passphrase:'unlock-passphrase'});
  const encrypted=copy(first.db.state.settings.encrypted_key);
  assert.equal((await first.api('/settings','POST',{base_url:'https://provider.test/v1',model:'second-model',remember:true})).status,200);
  assert.deepEqual(first.db.state.settings.encrypted_key,encrypted);first.runtime.close();
  const reopened=await setup(t,network,first.db);
  assert.equal((await reopened.api('/settings')).data.locked,true);
  assert.equal((await reopened.api('/settings','POST',{base_url:'https://provider.test/v1',model:'third-model',remember:true})).status,200);
  assert.deepEqual(first.db.state.settings.encrypted_key,encrypted);
  assert.equal((await reopened.api('/chat/preflight','POST',{text:'Hello'})).status,401);
  assert.equal((await reopened.api('/settings/unlock','POST',{passphrase:'unlock-passphrase'})).status,200);
  assert.equal((await reopened.api('/settings/test','POST',{})).status,200);
});
test('an interrupted running job is retained and never replayed',async t=>{
  const db=new MemoryDB();db.state.jobs.push({id:'interrupted-001',message:'Do something',status:'running',progress:[],user_message_id:'user-001'});
  const {api}=await setup(t,undefined,db);
  await waitFor(()=>db.state.jobs[0].status==='interrupted');
  const state=await api('/chat/state');assert.equal(state.data.jobs[0].status,'interrupted');
  assert.equal(db.state.tasks.length,0);
});
test('attention clicks are read-only and use no tools when a key is configured',async t=>{
  const calls=[],{api,db}=await setup(t,async(url,options)=>{calls.push(JSON.parse(options.body));return provider({role:'assistant',content:'How is the selected action going?'})});
  let id,actionId;
  await db.write(s=>{const m=new Model(s),task=m.create('Parent','Context');id=task.id;actionId=m.add(id,'action','Selected action').id;m.add(id,'action','Sibling');return null});
  await save(api);const before=JSON.stringify({tasks:db.state.tasks,entries:db.state.entries});
  await api('/chat/jobs','POST',{request_id:'attention-001',attention:{task_id:id,action_id:actionId}});
  await waitFor(()=>db.state.jobs[0]?.status==='done');assert.equal(calls.length,1);assert.ok(!('tools' in calls[0]));
  assert.equal(JSON.stringify({tasks:db.state.tasks,entries:db.state.entries}),before);
  const invalid=await api('/chat/jobs','POST',{request_id:'attention-002',attention:{task_id:id,action_id:'missing'}});assert.equal(invalid.status,422);
});
test('network errors explain browser CORS and never retry an ambiguous call',async t=>{
  let calls=0;const {api,db}=await setup(t,async()=>{calls++;throw TypeError('Failed to fetch')});await save(api);
  await api('/chat/jobs','POST',{request_id:'network-failure-001',text:'Hello'});
  await waitFor(()=>db.state.jobs[0]?.status==='error');assert.equal(calls,1);assert.match(db.state.jobs[0].error,/CORS/);
  assert.equal(db.state.jobs[0].changes_saved,false);assert.equal((await api('/settings')).data.has_key,true);
});
test('live attention drops changed AI suggestions and keeps current due items without another provider call',async t=>{
  const ids=[];let calls=0;
  const {api,db}=await setup(t,async()=>{calls++;return provider({role:'assistant',content:JSON.stringify({items:ids.map(id=>({id,reason:'Old reason'}))})})});
  for(const title of ['First decision','Second decision'])ids.push((await api('/threads','POST',{title})).data.id);
  await save(api);assert.equal((await api('/attention?force=true')).data.items.length,2);
  await api('/threads/'+ids[0],'PATCH',{summary:'Decision is updated'});
  assert.deepEqual((await api('/attention')).data.items.map(item=>item.id),[ids[1]]);
  await api('/threads/'+ids[0],'PATCH',{title:'Current title',revisit_at:'2020-01-01T12:00:00Z'});
  let items=(await api('/attention')).data.items;assert.equal(items.length,2);
  assert.equal(items.find(item=>item.id===ids[0]).title,'Current title');
  await api('/threads/'+ids[0],'PATCH',{revisit_at:'2035-01-01T12:00:00Z'});
  assert.deepEqual((await api('/attention')).data.items.map(item=>item.id),[ids[1]]);assert.equal(calls,1);
});
test('saved action completion is reflected in attention even if the chat then fails',async t=>{
  let actionId,calls=0;const {api,db}=await setup(t,async()=>{
    if(++calls>1)throw TypeError('Failed to fetch');
    return provider({role:'assistant',content:null,tool_calls:[{id:'finish-action',type:'function',function:{name:'update_action',arguments:JSON.stringify({action_id:actionId,done:true})}}]});
  });
  const task=(await api('/threads','POST',{title:'Action parent'})).data;
  actionId=(await api('/threads/'+task.id+'/entries','POST',{kind:'action',body:'Action to finish'})).data.id;
  await api('/actions/'+actionId,'PATCH',{revisit_at:'2020-01-01T12:00:00Z'});
  assert.equal((await api('/attention')).data.items.length,1);
  const tool={type:'function',function:{name:'update_action',parameters:{type:'object',required:['action_id'],properties:{action_id:{type:'string'},done:{type:'boolean'}}}}};
  config.tools.push(tool);t.after(()=>config.tools.pop());
  await save(api);await api('/chat/jobs','POST',{request_id:'attention-failed-001',text:'Complete this action'});
  await waitFor(()=>db.state.jobs[0]?.status==='error');assert.equal(db.state.jobs[0].changes_saved,true);
  assert.equal((await api('/attention')).data.items.length,0);
});
test('errors only flag saved changes after a task mutation commits',async t=>{
  let calls=0;const {api,db}=await setup(t,async()=>{
    if(++calls>1)throw TypeError('Failed to fetch');
    return provider({role:'assistant',content:null,tool_calls:[{id:'capture-once',type:'function',function:{name:'capture',arguments:'{"title":"Saved before failure"}'}}]});
  });await save(api);await api('/chat/jobs','POST',{request_id:'partial-changes-001',text:'Save a task'});
  await waitFor(()=>db.state.jobs[0]?.status==='error');assert.equal(calls,2);
  assert.equal(db.state.jobs[0].changes_saved,true);assert.equal(db.state.tasks.length,1);
});
test('unreadable provider responses are not misreported as browser CORS failures',async t=>{
  const {api,db}=await setup(t,async()=>new Response('<html>Not an API</html>'));await save(api);
  const result=await api('/settings/test','POST',{});assert.equal(result.status,422);assert.match(result.data.detail,/unreadable response/);
  assert.equal((await api('/settings')).data.has_key,true);assert.equal(db.state.jobs.length,0);
});
test('retired audio API does not send a recording or require a key',async t=>{
  let calls=0;const {runtime,db}=await setup(t,async()=>{calls++;throw Error('Unexpected network call')});
  const body=new FormData();body.append('file',new Blob(['audio'],{type:'audio/wav'}),'voice.wav');
  const result=await runtime.fetch(config.origin+config.base+'api/voice/transcribe',{method:'POST',body});
  assert.equal(result.status,410);assert.match((await result.json()).detail,/this device/);
  assert.equal(calls,0);assert.equal(db.state.messages.length,0);assert.equal(db.state.jobs.length,0);
});
test('model discovery uses unsaved fields without saving or sending chat requests',async t=>{
  const calls=[],{api,db}=await setup(t,async(url,options)=>{
    calls.push({url,options});return Response.json({data:[{id:'tool-mini',supported_parameters:['tools']},{id:'tool-mini',supported_parameters:['tools']},{id:'embedding-model'},{bad:'missing ID'}]});
  });
  const result=await api('/settings/models','POST',{base_url:'https://provider.test/v1/',api_key:'  typed-key  '});
  assert.deepEqual(result.data.models,['tool-mini']);
  assert.equal(calls[0].url,'https://provider.test/v1/models');assert.equal(calls[0].options.method,'GET');
  assert.equal(calls[0].options.headers.Authorization,'Bearer typed-key');
  assert.deepEqual(db.state.settings,{});assert.equal((await api('/settings')).data.has_key,false);
  await save(api,'saved-key');await api('/settings/models','POST',{});
  assert.equal(calls[1].options.headers.Authorization,'Bearer saved-key');
  assert.equal((await api('/settings/models','POST',{base_url:'https://another.test/v1'})).status,401);
  assert.equal(calls.length,2);assert.equal((await api('/settings')).data.has_key,true);
});
test('billing 429 errors explain the specific cause and never retry or discard the key',async t=>{
  for(const code of ['insufficient_quota','credit_balance_exhausted','project_spend_limit_exceeded','organization_usage_limit_exceeded']){
    let calls=0;const {api}=await setup(t,async()=>{calls++;return Response.json({error:{code,type:'insufficient_quota'}},{status:429})});
    await api('/settings','POST',{base_url:'https://api.openai.com/v1',model:'test',api_key:'valid-key'});
    const result=await api('/settings/test','POST',{});
    assert.equal(result.status,422);assert.match(result.data.detail,new RegExp(code));assert.match(result.data.detail,/ChatGPT subscriptions do not include API credit/);
    assert.equal(calls,1);assert.equal((await api('/settings')).data.has_key,true);
  }
});
test('temporary 429 respects Retry-After and retries a rejected request with the current key',async t=>{
  const pauses=[];let calls=0;
  const {api}=await setup(t,async(url,options)=>{
    assert.equal(options.headers.Authorization,'Bearer current-key');
    assert.ok(!('max_tokens' in JSON.parse(options.body)));
    return ++calls===1?Response.json({error:{code:'rate_limit_exceeded'}},{status:429,headers:{'Retry-After':'3'}}):provider({content:'OK'});
  },undefined,undefined,{pause:async ms=>{pauses.push(ms)}});
  await save(api,'current-key');assert.equal((await api('/settings/test','POST',{})).status,200);
  assert.equal(calls,2);assert.deepEqual(pauses,[3000]);
});
test('long rate limit delays are shown without retrying early',async t=>{
  let calls=0;const {api}=await setup(t,async()=>{calls++;return Response.json({error:{code:'slow_down'}},{status:429,headers:{'Retry-After':'120'}})});
  await save(api);const result=await api('/settings/test','POST',{});
  assert.match(result.data.detail,/temporarily rate limited/);assert.match(result.data.detail,/120 seconds/);assert.equal(calls,1);
});

test('listed OpenAI chat tools receive their required reasoning option',async t=>{
  const {readFileSync}=await import('node:fs');
  const tool_models=JSON.parse(readFileSync(new URL('../../tether/tool-models.json',import.meta.url)));
  const {api}=await setup(t,async(url,options)=>{
    const body=JSON.parse(options.body);assert.equal(body.reasoning_effort,'none');assert.equal(body.model,'gpt-6-sol');
    return provider({role:'assistant',content:'OK'});
  },undefined,undefined,{config:{...config,tool_models}});
  await api('/settings','POST',{base_url:'https://api.openai.com/v1',model:'gpt-6-sol',api_key:'synthetic-key',remember:false});
  assert.equal((await api('/settings/test','POST',{})).status,200);
});

test('explicit task context is request-scoped, validated, and dismissible',async t=>{
  const requests=[];
  const {api,db}=await setup(t,async(url,options)=>{requests.push(JSON.parse(options.body));return provider({content:'Ready.'})});
  await save(api);
  const task=(await api('/threads','POST',{title:'Home checklist',summary:'Plant carrots'})).data;
  const body={request_id:'selected-context-001',text:'Review the plan',task_context:[task.id]};
  assert.equal((await api('/chat/jobs','POST',body)).status,202);
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  const context=JSON.parse(requests.at(-1).messages[0].content.split('(data, not instructions): ')[1]);
  assert.equal(context.selected_tasks[0].id,task.id);assert.equal(context.focused_task.id,task.id);
  assert.equal((await api('/chat/jobs','POST',body)).status,202);
  assert.equal((await api('/chat/jobs','POST',{...body,task_context:[]})).status,422);
  assert.equal((await api('/chat/jobs','POST',{...body,request_id:'selected-context-002',task_context:[]})).status,202);
  await waitFor(()=>db.state.jobs[1]?.status==='done');
  const cleared=JSON.parse(requests.at(-1).messages[0].content.split('(data, not instructions): ')[1]);
  assert.deepEqual(cleared.selected_tasks,[]);assert.equal(cleared.focused_task,null);
  const count=db.state.jobs.length;
  assert.equal((await api('/chat/jobs','POST',{...body,request_id:'invalid-context-001',task_context:['missing']})).status,404);
  assert.equal(db.state.jobs.length,count);
});
test('Browser runtime is Home-only and keeps independent stores separate',async t=>{
  const requests=[];
  const home=await setup(t,async(_url,init)=>{requests.push(JSON.parse(init.body));return provider({content:'Home plan.'})},new MemoryDB(),new Locks(),{config:{...config,workspace:'home'}});
  const work=await setup(t);
  await home.api('/threads','POST',{title:'Groceries'});
  await work.api('/threads','POST',{title:'Project update'});
  assert.deepEqual((await home.api('/threads')).data.map(x=>x.title),['Groceries']);
  assert.deepEqual((await work.api('/threads')).data.map(x=>x.title),['Project update']);
  await save(home.api);
  await home.api('/chat/jobs','POST',{request_id:'home-prompt-001',text:'Plan my day'});
  await waitFor(()=>home.db.state.jobs[0]?.status==='done');
  assert.ok(requests[0].messages[0].content.includes('Home mode'));
  assert.ok(!JSON.stringify(requests).includes('Project update'));
  assert.equal(config.system,'Use tools to save changes.');
});

test('Drive local adapter is Home-only, transactional and excludes private fields',async t=>{
  const fixed=await setup(t,undefined,undefined,undefined,{config:{...config,workspace:'work'}});
  assert.equal((await fixed.api('/portable')).data.workspace,'home');
  assert.equal((await fixed.api('/threads?workspace=work')).status,403);
  const home=await setup(t,undefined,undefined,undefined,{config:{...config,workspace:'home'}});
  const task=(await home.api('/threads','POST',{title:'Milk'})).data;
  home.db.state.messages.push({id:'m',role:'user',body:'Private conversation',created_at:new Date().toISOString()});
  home.db.state.settings.api_key='secret';home.db.state.tasks[0].action_prompt='Private AI instruction';
  const s=(await home.api('/drive-sync/local')).data;
  assert.equal(JSON.stringify(s).includes('Private'),false);assert.equal(JSON.stringify(s).includes('secret'),false);
  const changed=copy(s.records);changed['task:'+task.id].title='Bread';
  const result=await home.api('/drive-sync/local','POST',{expected:s.records,expected_revision:s.revision,records:changed,metadata:{queue:[]}});
  assert.equal(result.status,200);assert.equal(home.db.state.tasks[0].title,'Bread');assert.equal(home.db.state.tasks[0].action_prompt,'Private AI instruction');
  assert.equal((await home.api('/drive-sync/local','POST',{expected:s.records,expected_revision:s.revision,records:s.records,metadata:{}})).status,409);
  const now=result.data;const injected=copy(now.records);injected['task:'+task.id].api_key='bad';
  assert.equal((await home.api('/drive-sync/local','POST',{expected:now.records,expected_revision:now.revision,records:injected,metadata:{}})).status,422);
  const backup=(await home.api('/portable')).data;assert.equal(JSON.stringify(backup).includes('queue'),false);
});

test('Work and unlabelled imports require explicit Home consent',async t=>{
 const {api}=await setup(t);const portable=(await api('/portable')).data;
 for(const workspace of ['work',undefined]){
  const incoming={...portable,workspace};
  assert.equal((await api('/import','POST',incoming)).status,409);
  assert.equal((await api('/import','POST',{...incoming,home_import_confirmed:true})).status,200);
 }
});

test('Stop aborts a pending provider and late completion cannot run tools or overwrite status',async t=>{
  let release,signal;const {api,db}=await setup(t,async(url,options)=>{signal=options.signal;await new Promise(r=>release=r);return provider({tool_calls:[{id:'late-tool',function:{name:'capture',arguments:'{"title":"Must not exist"}'}}]})});await save(api);
  await api('/chat/jobs','POST',{request_id:'stop-pending-001',text:'Save a task'});await waitFor(()=>release);
  const stopped=await api('/chat/jobs/stop-pending-001/cancel','POST',{});assert.equal(stopped.data.status,'interrupted');assert.ok(signal.aborted);
  release();await new Promise(r=>setTimeout(r,20));assert.equal(db.state.tasks.length,0);assert.equal(db.state.jobs[0].status,'interrupted');assert.equal(db.state.messages.length,1);
  assert.equal((await api('/chat/jobs/stop-pending-001/cancel','POST',{})).data.status,'interrupted');
});
test('interrupt includes completed outcome context once and starts new request without replaying tools',async t=>{
  let count=0,waiting,continued;const {api,db}=await setup(t,async(url,options)=>{
    count++;if(count===1)return provider({tool_calls:[{id:'saved-tool',function:{name:'capture',arguments:'{"title":"Saved before stop"}'}}]});
    if(count===2){waiting=true;return new Promise(()=>{})}
    continued=JSON.parse(options.body);return provider({content:'Updated context received.'});
  });await save(api);await api('/chat/jobs','POST',{request_id:'interrupt-first',text:'Record the original request'});await waitFor(()=>waiting);
  assert.equal(db.state.tasks.length,1);await api('/chat/jobs/interrupt-first/cancel','POST',{});
  const body={request_id:'interrupt-second',text:'Actually add this detail',interrupt_job_id:'interrupt-first'};
  assert.equal((await api('/chat/jobs','POST',body)).status,202);assert.equal((await api('/chat/jobs','POST',body)).status,202);
  await waitFor(()=>db.state.jobs[1]?.status==='done');assert.equal(db.state.tasks.length,1);assert.equal(count,3);
  assert.ok(JSON.stringify(continued).includes('Saved before stop'));assert.ok(JSON.stringify(continued).includes('Record the original request'));
  assert.equal(continued.messages.filter(m=>m.content==='Actually add this detail').length,1);
});
test('Stop during response read and retry backoff does not retry',async t=>{
  for(const mode of ['read','retry']){
    let count=0,waiting=false;
    const {api,db}=await setup(t,async()=>{count++;if(mode==='read')return {ok:true,json:()=>{waiting=true;return new Promise(()=>{})}};return new Response('busy',{status:429,headers:{'Retry-After':'1'}})},new MemoryDB(),new Locks(),{pause:()=>{waiting=true;return new Promise(()=>{})}});
    await save(api);await api('/chat/jobs','POST',{request_id:'stop-'+mode+'-001',text:'Hello'});await waitFor(()=>waiting);
    await api('/chat/jobs/stop-'+mode+'-001/cancel','POST',{});await new Promise(r=>setTimeout(r,15));assert.equal(count,1);assert.equal(db.state.jobs[0].status,'interrupted');
  }
});

test('provider request has no application elapsed timeout beyond the old 60 second limit',async t=>{
  let release,signal;const {api,db}=await setup(t,async(url,options)=>{signal=options.signal;return new Promise(resolve=>release=()=>resolve(provider({content:'Long request finished.'})))});await save(api);
  t.mock.timers.enable({apis:['setTimeout']});
  await api('/chat/jobs','POST',{request_id:'long-provider-001',text:'Take time'});
  for(let i=0;i<30&&!release;i++)await Promise.resolve();assert.ok(release);
  t.mock.timers.tick(65000);await Promise.resolve();assert.equal(signal.aborted,false);assert.equal(db.state.jobs[0].status,'running');
  release();for(let i=0;i<40&&db.state.jobs[0].status!=='done';i++)await Promise.resolve();assert.equal(db.state.jobs[0].status,'done');
  t.mock.timers.reset();
});

test('Stop in another tab aborts owner, queued Stop survives runtime reopen and is never replayed',async t=>{
  const db=new MemoryDB(),locks=new Locks();let signal,calls=0;
  const first=await setup(t,async(url,options)=>{calls++;signal=options.signal;return new Promise(()=>{})},db,locks);await save(first.api);
  await first.api('/chat/jobs','POST',{request_id:'cross-tab-running',text:'First'});await waitFor(()=>signal);
  await first.api('/chat/jobs','POST',{request_id:'cross-tab-queued',text:'Second'});
  const second=await setup(t,()=>{throw Error('Must not replay')},db,locks);
  await second.api('/chat/jobs/cross-tab-queued/cancel','POST',{});
  await second.api('/chat/jobs/cross-tab-running/cancel','POST',{});
  await waitFor(()=>signal.aborted);assert.equal(calls,1);assert.ok(db.state.jobs.every(j=>j.status==='interrupted'));
  first.runtime.close();second.runtime.close();const third=await setup(t,()=>{throw Error('Must not replay after reload')},db,locks);
  await third.api('/chat/state');assert.ok(db.state.jobs.every(j=>j.status==='interrupted'));
});

test('an unacknowledged stopped outbox is atomically interrupted before any provider call',async t=>{
  let calls=0;const {api,db}=await setup(t,()=>{calls++;throw Error('Must not execute stopped outbox')});await save(api);
  const body={request_id:'stopped-outbox-001',text:'Do not save this',stop_requested:true};
  assert.equal((await api('/chat/jobs','POST',body)).data.status,'interrupted');
  assert.equal((await api('/chat/jobs','POST',{...body,stop_requested:false})).data.status,'interrupted');
  await new Promise(r=>setTimeout(r,20));assert.equal(calls,0);assert.equal(db.state.messages.length,1);
});

test('curation cannot resurrect completed children or future occurrences as parent attention',async t=>{
  let ids=[];const {api}=await setup(t,()=>provider({content:JSON.stringify({items:ids.map(id=>({id,reason:'Due today'}))})}));
  await save(api);
  const parent=(await api('/threads','POST',{title:'Parent with finished child'})).data;
  const action=(await api('/threads/'+parent.id+'/entries','POST',{kind:'action',body:'Child'})).data;
  await api('/actions/'+action.id,'PATCH',{done:true});
  const future=(await api('/threads','POST',{title:'Tomorrow'})).data;
  await api('/threads/'+future.id,'PATCH',{recurrence:'daily',next_occurrence:'2035-01-01'});
  ids=[parent.id,future.id];
  assert.deepEqual((await api('/attention?force=true')).data.items,[]);
  await api('/threads/'+parent.id,'PATCH',{revisit_at:'2020-01-01T12:00:00Z'});
  assert.deepEqual((await api('/attention')).data.items.map(i=>i.id),[parent.id]);
});

test('daily reminder capture never injects one-shot dates and requires a recurrence tool',async t=>{
  let count=0,db;const setupResult=await setup(t,()=>{
    count++;
    if(count===1)return provider({content:null,tool_calls:[{id:'daily-capture',function:{name:'capture',arguments:'{"title":"Daily check-in"}'}}]});
    if(count===3){assert.equal(db.state.tasks[0].revisit_at,null);return provider({content:null,tool_calls:[{id:'daily-schedule',function:{name:'set_recurrence',arguments:JSON.stringify({id:db.state.tasks[0].id,frequency:'daily',next_occurrence:'2035-01-01T09:00:00Z',attention_mode:'occurrence'})}}]})}
    return provider({content:'Captured.'});
  },new MemoryDB(),new Locks(),{config:{...config,tools:[...config.tools,{type:'function',function:{name:'set_recurrence',parameters:{required:['id','frequency','next_occurrence']}}}]}});
  db=setupResult.db;const {api}=setupResult;
  await save(api);await api('/chat/jobs','POST',{request_id:'daily-capture-regression',text:'Remind me daily starting tomorrow'});
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  assert.equal(count,4);assert.equal(db.state.tasks[0].recurrence,'daily');
  assert.equal(db.state.tasks[0].revisit_at,null);assert.equal(db.state.tasks[0].due_at,null);
});
