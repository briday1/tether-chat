import test from 'node:test';
import assert from 'node:assert/strict';
import {HouseholdAI} from '../../web/household-ai-service.mjs';
import {sealHouseholdBundle} from '../../web/household-ai-crypto.mjs';
const id='revision_123',householdId='household_123',pass='synthetic test passphrase';
async function setup(){let applied=null,seals=0,active=null;const context={householdId,revisionId:id};const ciphertext=await sealHouseholdBundle({base_url:'https://provider.example/v1',model:'model',api_key:'synthetic-test-key'},pass,context);let versions=[{id,parents:[],ciphertext}];const storage=new Map();const sync={token:'synthetic-google',state:async()=>({metadata:{session:{spreadsheetId:householdId}}})};const runtime={householdAI:{use:async(b,c)=>{applied={b,c};active=c},lock:()=>{active=null},seal:async()=>{seals++;return ciphertext},status:async()=>({active:!!active})}};const store={read:async()=>({versions,tips:versions}),append:async()=>{}};const service=new HouseholdAI({sync,runtime,store,storage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)}});return {service,sync,runtime,store,storage,getApplied:()=>applied,getSeals:()=>seals,setVersions:v=>versions=v}}
test('unlock requires explicit endpoint review; confirmation persists only public pin',async()=>{const x=await setup();await x.service.unlock(pass);assert.equal(x.getApplied(),null);await assert.rejects(x.service.confirm());await x.service.confirm({confirmed:true});assert.equal(x.getApplied().b.api_key,'synthetic-test-key');assert.ok(!JSON.stringify([...x.storage]).includes('synthetic-test-key'));assert.ok(!JSON.stringify([...x.storage]).includes(pass));assert.equal((await x.service.status()).pending,null)});
test('wrong passphrase, conflicting revisions and cancellation cannot install a key',async()=>{const x=await setup();await assert.rejects(x.service.unlock('wrong synthetic passphrase'));await x.service.unlock(pass);x.service.cancel();await assert.rejects(x.service.confirm({confirmed:true}));x.setVersions([{id:'one'}, {id:'two'}]);await assert.rejects(x.service.unlock(pass),/conflicting/);assert.equal(x.getApplied(),null)});
test('encrypted publication requires confirmation and close during crypto prevents upload',async()=>{const x=await setup();await assert.rejects(x.service.publish(pass));assert.equal(x.getSeals(),0);let finish,appends=0;x.runtime.householdAI.seal=()=>new Promise(r=>finish=r);x.store.append=async()=>{appends++};const publish=x.service.publish(pass,{confirmed:true});while(!finish)await new Promise(r=>setTimeout(r,0));x.service.cancel();finish('opaque');await assert.rejects(publish,/cancelled/);assert.equal(appends,0)});
test('a different endpoint/revision is flagged and never silently installed',async()=>{const x=await setup();await x.service.unlock(pass);await x.service.confirm({confirmed:true});const ciphertext=await sealHouseholdBundle({base_url:'https://other.example/v1',model:'new-model',api_key:'synthetic-new'},pass,{householdId,revisionId:'revision_456'});x.setVersions([{id:'revision_456',parents:[id],ciphertext}]);const result=await x.service.unlock(pass);assert.equal(result.changed,true);assert.equal(x.getApplied().b.base_url,'https://provider.example/v1');await x.service.confirm({confirmed:true});assert.equal(x.getApplied().b.base_url,'https://other.example/v1')});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}};
test('cancellation while confirmation awaits selected household never activates or pins key',async()=>{
  const x=await setup();await x.service.unlock(pass);
  const gate=deferred();x.sync.state=()=>gate.promise;
  const confirmation=x.service.confirm({confirmed:true});x.service.cancel();
  gate.resolve({metadata:{session:{spreadsheetId:householdId}}});
  await assert.rejects(confirmation,/cancelled/);assert.equal(x.getApplied(),null);assert.equal(x.storage.size,0);
});
test('lock while confirmation awaits runtime use cannot reactivate or persist a pin',async()=>{
  const x=await setup();await x.service.unlock(pass);
  const entered=deferred(),gate=deferred();let active=false;
  x.runtime.householdAI.use=async(b,context)=>{entered.resolve();await gate.promise;if(context.isActive&&!context.isActive())throw Error('Unlock was cancelled.');active=true};
  x.runtime.householdAI.lock=()=>{active=false};
  const confirmation=x.service.confirm({confirmed:true});await entered.promise;x.service.lock();gate.resolve();
  await assert.rejects(confirmation,/cancelled/);assert.equal(active,false);assert.equal(x.storage.size,0);
});
test('selected household changing while publication seals prevents uploading to either household',async()=>{
  const x=await setup(),entered=deferred(),gate=deferred();let appends=0;
  x.runtime.householdAI.seal=async()=>{entered.resolve();return gate.promise};x.store.append=async()=>{appends++};
  const publication=x.service.publish(pass,{confirmed:true});await entered.promise;
  x.sync.state=async()=>({metadata:{session:{spreadsheetId:'different_household'}}});gate.resolve('opaque-synthetic');
  await assert.rejects(publication,/household changed/);assert.equal(appends,0);
});
test('household switch while append awaits transport invalidates upload guard',async()=>{
  const x=await setup(),entered=deferred(),gate=deferred();let uploads=0;x.sync.generation=0;
  x.store.append=async(token,session,version,{isActive})=>{entered.resolve();await gate.promise;if(!isActive())throw Error('Household setup was cancelled.');uploads++};
  const publication=x.service.publish(pass,{confirmed:true});await entered.promise;
  x.sync.generation++;x.sync.state=async()=>({metadata:{session:{spreadsheetId:'different_household'}}});gate.resolve();
  await assert.rejects(publication,/cancelled/);assert.equal(uploads,0);
});
