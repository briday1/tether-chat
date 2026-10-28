import test from 'node:test';
import assert from 'node:assert/strict';
import {createRuntime} from '../../web/runtime.mjs';
import {emptyState,copy} from '../../web/store.mjs';
import {openHouseholdBundle} from '../../web/household-ai-crypto.mjs';
class DB {constructor(){this.state=emptyState()}async read(fn){return copy(fn(this.state))}async write(fn){const next=copy(this.state),result=fn(next);this.state=next;return copy(result)}}
const config={base:'/test/',origin:'https://app.test',version:'test',system:'',tools:[]};
async function setup(t){const db=new DB(),values=new Map(),requests=[];const runtime=await createRuntime({config,db,session:{getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)},network:async(url,options)=>{requests.push({url,options});return Response.json({choices:[{message:{content:'ok'}}]})}});t.after(()=>runtime.close());const api=async(path,body)=>{const response=await runtime.fetch('https://app.test/test/api'+path,{method:body===undefined?'GET':'POST',body:body===undefined?undefined:JSON.stringify(body)});return {status:response.status,data:await response.json()}};db.state.drive_sync={metadata:{session:{spreadsheetId:'household_123'}},revision:0};await api('/settings',{base_url:'https://personal.example/v1',model:'personal-model',api_key:'synthetic-personal',remember:false});return {db,values,requests,runtime,api}}
test('household override is session-only and never replaces personal config or appears in backup',async t=>{const {db,values,requests,runtime,api}=await setup(t);const personal=copy(db.state.settings);await runtime.householdAI.use({base_url:'https://shared.example/v1',model:'shared-model',api_key:'synthetic-shared'},{householdId:'household_123',revisionId:'revision_123',confirmed:true});assert.equal((await api('/settings')).data.household_active,true);assert.equal((await api('/settings/test',{})).status,200);assert.equal(requests[0].url,'https://shared.example/v1/chat/completions');assert.equal(requests[0].options.redirect,'error');assert.equal(requests[0].options.headers.Authorization,'Bearer synthetic-shared');assert.deepEqual(db.state.settings,personal);assert.ok(!JSON.stringify(db.state).includes('synthetic-shared'));assert.ok(!JSON.stringify([...values]).includes('synthetic-shared'));assert.ok(!JSON.stringify((await api('/backup')).data).includes('synthetic-shared'));runtime.householdAI.lock();await api('/settings/test',{});assert.equal(requests.at(-1).url,'https://personal.example/v1/chat/completions')});
test('wrong household, missing confirmation and unsafe endpoint cannot activate shared key',async t=>{const {runtime,requests}=await setup(t);const b={base_url:'https://shared.example/v1',model:'model',api_key:'synthetic-shared'};await assert.rejects(runtime.householdAI.use(b,{householdId:'other_group',revisionId:'revision_123',confirmed:true}));await assert.rejects(runtime.householdAI.use(b,{householdId:'household_123',revisionId:'revision_123'}));await assert.rejects(runtime.householdAI.use({...b,base_url:'https://127.0.0.1/v1'},{householdId:'household_123',revisionId:'revision_123',confirmed:true}));assert.equal(requests.length,0)});
test('owner seal uses personal connection, selected household binding, and produces only opaque ciphertext',async t=>{const {runtime}=await setup(t),context={householdId:'household_123',revisionId:'revision_123'};await assert.rejects(runtime.householdAI.seal('synthetic passphrase only',{...context,householdId:'other_group'}));const text=await runtime.householdAI.seal('synthetic passphrase only',context);assert.ok(!text.includes('synthetic-personal'));const c=await openHouseholdBundle(text,'synthetic passphrase only',context);assert.equal(c.api_key,'synthetic-personal');assert.equal(c.base_url,'https://personal.example/v1')});
test('disconnect or switch never keeps sending household key',async t=>{const {db,runtime,api,requests}=await setup(t);await runtime.householdAI.use({base_url:'https://shared.example/v1',model:'m',api_key:'synthetic-shared'},{householdId:'household_123',revisionId:'revision_123',confirmed:true});db.state.drive_sync.metadata.session=null;await api('/settings/test',{});assert.ok(!requests.some(r=>r.options.headers.Authorization==='Bearer synthetic-shared'))});
test('unlocking encrypted personal settings while shared is active restores only the personal URL and key',async t=>{
  const {runtime,api,requests}=await setup(t);
  assert.equal((await api('/settings',{base_url:'https://personal.example/v1',model:'personal-model',api_key:'synthetic-personal',remember:true,passphrase:'synthetic personal passphrase'})).status,200);
  await api('/settings/lock',{});
  await runtime.householdAI.use({base_url:'https://shared.example/v1',model:'shared-model',api_key:'synthetic-shared'},{householdId:'household_123',revisionId:'revision_123',confirmed:true});
  const unlocked=await api('/settings/unlock',{passphrase:'synthetic personal passphrase'});
  assert.equal(unlocked.status,200);assert.equal(unlocked.data.base_url,'https://personal.example/v1');assert.ok(!unlocked.data.household_active);
  assert.equal((await api('/settings/test',{})).status,200);
  assert.equal(requests.at(-1).url,'https://personal.example/v1/chat/completions');
  assert.equal(requests.at(-1).options.headers.Authorization,'Bearer synthetic-personal');
  assert.ok(!requests.some(r=>r.url.startsWith('https://shared.example')&&r.options.headers.Authorization==='Bearer synthetic-personal'));
});
test('model discovery never reuses shared key for changed endpoint, including same host different path',async t=>{
  const {runtime,api,requests}=await setup(t);
  await runtime.householdAI.use({base_url:'https://shared.example/v1',model:'m',api_key:'synthetic-shared'},{householdId:'household_123',revisionId:'revision_123',confirmed:true});
  for(const base_url of ['https://other.example/v1','https://shared.example/v2','https://shared.example:8443/v1']){
    assert.equal((await api('/settings/models',{base_url})).status,401);
  }
  assert.equal(requests.length,0);
  await api('/settings/models',{base_url:'https://shared.example/v1'});
  assert.equal(requests.length,1);assert.equal(requests[0].url,'https://shared.example/v1/models');
  assert.equal(requests[0].options.headers.Authorization,'Bearer synthetic-shared');assert.equal(requests[0].options.redirect,'error');
});
test('locking while runtime confirmation is awaiting database read cannot reactivate shared key',async t=>{
  const {db,runtime,api,requests}=await setup(t);
  const original=db.read.bind(db);let release,entered;
  const arrived=new Promise(r=>entered=r),gate=new Promise(r=>release=r);
  db.read=async fn=>{entered();await gate;return original(fn)};
  const use=runtime.householdAI.use({base_url:'https://shared.example/v1',model:'m',api_key:'synthetic-shared'},{householdId:'household_123',revisionId:'revision_123',confirmed:true});
  await arrived;runtime.householdAI.lock();release();await assert.rejects(use,/cancelled|locked/i);db.read=original;
  await api('/settings/test',{});assert.equal(requests.at(-1).options.headers.Authorization,'Bearer synthetic-personal');
});

for(const change of ['provider','lock'])test(`pending personal unlock cannot reactivate or rebind key after ${change} change`,async t=>{
  const {api,requests}=await setup(t);
  await api('/settings',{base_url:'https://personal.example/v1',model:'m',api_key:'synthetic-personal',remember:true,passphrase:'synthetic personal passphrase'});
  await api('/settings/lock',{});
  const derive=crypto.subtle.deriveKey.bind(crypto.subtle);let enter,release;
  const entered=new Promise(r=>enter=r),gate=new Promise(r=>release=r);
  const mocked=t.mock.method(crypto.subtle,'deriveKey',async(...args)=>{enter();await gate;return derive(...args)});
  const unlocking=api('/settings/unlock',{passphrase:'synthetic personal passphrase'});
  await entered;
  if(change==='provider')await api('/settings',{base_url:'https://changed.example/v1',model:'m',api_key:'synthetic-new',remember:false});
  else await api('/settings/lock',{});
  release();const result=await unlocking;mocked.mock.restore();
  assert.equal(result.status,422);assert.match(result.data.detail,/changed while unlocking/i);
  const connection=await api('/settings/test',{});
  if(change==='provider'){
    assert.equal(connection.status,200);assert.equal(requests.at(-1).url,'https://changed.example/v1/chat/completions');
    assert.equal(requests.at(-1).options.headers.Authorization,'Bearer synthetic-new');
  }else{assert.equal(connection.status,401);assert.equal(requests.length,0)}
  assert.ok(!requests.some(r=>r.url.startsWith('https://changed.example')&&r.options.headers.Authorization==='Bearer synthetic-personal'));
});

test('locking while remembered provider save encrypts cannot reactivate the key',async t=>{
  const {api,requests}=await setup(t);
  const derive=crypto.subtle.deriveKey.bind(crypto.subtle);let enter,release;
  const entered=new Promise(r=>enter=r),gate=new Promise(r=>release=r);
  const mocked=t.mock.method(crypto.subtle,'deriveKey',async(...args)=>{enter();await gate;return derive(...args)});
  const saving=api('/settings',{base_url:'https://personal.example/v1',model:'m',api_key:'synthetic-personal',remember:true,passphrase:'synthetic personal passphrase'});
  await entered;await api('/settings/lock',{});release();const result=await saving;mocked.mock.restore();
  assert.equal(result.status,422);assert.match(result.data.detail,/changed while saving/i);
  assert.equal((await api('/settings/test',{})).status,401);assert.equal(requests.length,0);
});
