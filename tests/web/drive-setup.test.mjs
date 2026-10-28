import test from 'node:test';import assert from 'node:assert/strict';
import {HouseholdSetup} from '../../web/drive-setup.mjs';
const household={id:'sheet_123456',name:'Our household',sheetId:0};
function memory(){const data=new Map();return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key),data}}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
function locks(){let held=false;return {async request(key,options,fn){if(held)return fn(null);held=true;try{return await fn({name:key})}finally{held=false}}}}
function fixture(){
 const storage=memory(),calls=[],lock=locks();
 const transport={createHousehold:async()=>{calls.push('create');return household},inspectHousehold:async()=>{calls.push('inspect');return household}};
 const activate=async()=>{calls.push('activate')};const make=(options={})=>new HouseholdSetup({transport,localStorage:storage,storageKey:'setup',activate,locks:lock,...options});
 return {storage,calls,transport,make,setup:make()};
}
test('create persists intent before request, confirms before activate, excludes tokens',async()=>{
 const f=fixture();f.transport.createHousehold=async()=>{const s=JSON.parse(f.storage.getItem('setup'));assert.equal(s.inflight,'create');assert.equal(s.kind,'create');assert.ok(!JSON.stringify(s).includes('SECRET'));return household};
 const setup=f.make({activate:async(h)=>{assert.deepEqual(h,household);assert.deepEqual(JSON.parse(f.storage.getItem('setup')).household,household)}});
 assert.deepEqual(await setup.create('SECRET',{name:'Our household'}),household);assert.equal(setup.state(),null);
});
test('stop while creating retains confirmed result and prevents activation',async()=>{
 const f=fixture(),pending=deferred(),entered=deferred();f.transport.createHousehold=async()=>{f.calls.push('create');entered.resolve();return pending.promise};
 const run=f.setup.create('secret',{name:'Home'});await entered.promise;f.setup.stop();pending.resolve(household);await assert.rejects(run,e=>e.status===499);
 assert.deepEqual(f.calls,['create']);assert.deepEqual(f.setup.state().household,household);await f.make().resume('fresh');assert.deepEqual(f.calls,['create','activate']);
});
test('unknown creation never automatically repeats, including explicit errors',async()=>{
 for(const error of [new Error('offline'),Object.assign(new Error('refused'),{status:401})]){
  const f=fixture();f.transport.createHousehold=async()=>{f.calls.push('create');throw error};await assert.rejects(f.setup.create('secret',{name:'Home'}));
  await assert.rejects(f.make().resume('fresh'),/unconfirmed/);assert.deepEqual(f.calls,['create']);
 }
});
test('readonly join inspection safely retries after failure',async()=>{
 const f=fixture();let first=true;f.transport.inspectHousehold=async()=>{f.calls.push('inspect');if(first){first=false;throw Error('offline')}return household};
 await assert.rejects(f.setup.join('secret',{id:household.id}),/offline/);await f.make().resume('fresh');assert.deepEqual(f.calls,['inspect','inspect','activate']);
});
test('activation failure retains confirmed household and repeats activation only',async()=>{
 const f=fixture();let first=true;const activate=async()=>{f.calls.push('activate');if(first){first=false;throw Error('Partial configuration')}};
 await assert.rejects(f.make({activate}).create('secret',{name:'Home'}),/Partial/);await f.make({activate}).resume('fresh');assert.deepEqual(f.calls,['create','activate','activate']);
});
test('abandon never resurrects confirmed late response or deletes remote Sheet',async()=>{
 const f=fixture(),pending=deferred(),entered=deferred();f.transport.createHousehold=async()=>{f.calls.push('create');entered.resolve();return pending.promise};
 const run=f.setup.create('secret',{name:'Home'});await entered.promise;f.setup.abandon();pending.resolve(household);await assert.rejects(run,e=>e.status===499);assert.equal(f.setup.state(),null);assert.deepEqual(f.calls,['create']);
});
test('cross-tab lock guards creation and fresh pending state blocks duplicate start',async()=>{
 const f=fixture(),pending=deferred(),entered=deferred();f.transport.createHousehold=async()=>{entered.resolve();return pending.promise};const run=f.setup.create('secret',{name:'Home'});await entered.promise;
 await assert.rejects(f.make().create('secret',{name:'Other'}),/another window/);f.setup.stop();pending.resolve(household);await assert.rejects(run,e=>e.status===499);
 await assert.rejects(f.make().create('secret',{name:'Other'}),/already exists/);
});
test('storage failure before intent prevents remote calls',async()=>{
 const f=fixture();f.storage.setItem=()=>{throw Error('full')};await assert.rejects(f.setup.create('secret',{name:'Home'}),/full/);assert.deepEqual(f.calls,[]);
});
test('confirmed result survives storage error in memory and can be persisted on resume',async()=>{
 const f=fixture(),save=f.storage.setItem;let fail=true;f.storage.setItem=(k,v)=>{if(fail&&JSON.parse(v).household)throw Error('full');save(k,v)};
 await assert.rejects(f.setup.create('secret',{name:'Home'}),/full/);assert.deepEqual(f.setup.state().household,household);fail=false;await f.setup.resume('fresh');assert.deepEqual(f.calls,['create','activate']);
});
test('stop after successful activation retains done marker without repeated activation',async()=>{
 const f=fixture(),pending=deferred(),entered=deferred();let control;const setup=f.make({activate:async(h,c)=>{control=c;entered.resolve();await pending.promise}});
 const run=setup.create('secret',{name:'Home'});await entered.promise;setup.stop();assert.equal(control.isActive(),false);pending.resolve();await assert.rejects(run,e=>e.status===499);assert.equal(setup.state().step,'done');await setup.resume('fresh');assert.equal(setup.state(),null);
});
test('saved state is bounded and unknown secret-bearing fields rejected',()=>{
 const f=fixture();for(const value of ['x'.repeat(8001),JSON.stringify({version:2,id:'intent_12345',kind:'create',step:'request',inflight:null,name:'Home',token:'secret'})]){f.storage.setItem('setup',value);assert.throws(()=>f.setup.state())}
});
test('invalid response and mismatched selected Sheet never activate',async()=>{
 const f=fixture();f.transport.inspectHousehold=async()=>({...household,id:'other_123456'});await assert.rejects(f.setup.join('secret',{id:household.id}),/different/);assert.deepEqual(f.calls,[]);
});
test('missing Web Locks fails closed without storing or sending',async()=>{
 const f=fixture();await assert.rejects(f.make({locks:null}).create('secret',{name:'Home'}),/Web Locks/);assert.equal(f.setup.state(),null);assert.deepEqual(f.calls,[]);
});
