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
async function setup(t,network,db=new MemoryDB(),locks=new Locks()){
  const values=new Map(),session={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
  const runtime=await createRuntime({config,db,locks,session,network:network||(()=>{throw Error('Unexpected provider request')})});t.after(()=>runtime.close());
  const api=async(path,method='GET',body)=>{
    const response=await runtime.fetch(config.origin+config.base+'api'+path,{method,body:body===undefined?undefined:JSON.stringify(body)});
    return {status:response.status,data:await response.json()};
  };
  return {runtime,api,db,session};
}
async function waitFor(check){for(let i=0;i<200;i++){const result=await check();if(result)return result;await new Promise(r=>setTimeout(r,5))}throw Error('Timed out waiting for queue')}
async function save(api,key='test-user-key'){return api('/settings','POST',{base_url:'https://provider.test/v1',model:'tool-model',api_key:key,remember:false})}
test('local commands run without a key and submissions are idempotent',async t=>{
  const {api,db}=await setup(t);const body={request_id:'request-local-001',text:'/brief'};
  const first=await api('/chat/jobs','POST',body),repeat=await api('/chat/jobs','POST',body);
  assert.equal(first.status,202);assert.equal(first.data.id,repeat.data.id);
  await waitFor(()=>db.state.jobs[0]?.status==='done');assert.equal(db.state.messages.length,2);
  const changed=await api('/chat/jobs','POST',{...body,text:'Different'});assert.equal(changed.status,422);
  assert.equal(db.state.messages.length,2);const state=await api('/chat/state');assert.ok(state.data.messages[1].html.includes('Daily brief'));
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
  assert.equal((await api('/settings','POST',{base_url:'https://another-provider.test/v1',model:'test',remember:false})).data.has_key,false);
  assert.ok(!session.getItem('tether-chat-web-key:'+config.base));
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
});
test('microphone recordings go directly to the configured provider without entering chat or backups',async t=>{
  const calls=[],{runtime,api,db}=await setup(t,async(url,options)=>{
    calls.push({url,options});assert.ok(options.body instanceof FormData);
    assert.equal(options.body.get('model'),'test-transcriber');assert.equal(options.headers.Authorization,'Bearer voice-test-key');
    return Response.json({text:'Review this spoken draft.'});
  });await save(api,'voice-test-key');
  const audio=new FormData();audio.append('file',new Blob(['synthetic audio'],{type:'audio/webm'}),'voice.webm');
  audio.append('model','test-transcriber');audio.append('provider_base','https://provider.test/v1');
  const result=await runtime.fetch(config.origin+config.base+'api/voice/transcribe',{method:'POST',body:audio});
  assert.deepEqual(await result.json(),{text:'Review this spoken draft.'});assert.equal(calls[0].url,'https://provider.test/v1/audio/transcriptions');
  assert.equal(db.state.messages.length,0);assert.equal(db.state.jobs.length,0);
  audio.set('provider_base','https://wrong.example/v1');
  assert.equal((await runtime.fetch(config.origin+config.base+'api/voice/transcribe',{method:'POST',body:audio})).status,422);
  assert.equal(calls.length,1);
});
