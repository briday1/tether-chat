import test from 'node:test';import assert from 'node:assert/strict';
import {HouseholdSetup} from '../../tether/drive-setup.mjs';
import {SyncError} from '../../tether/drive-sync-core.mjs';
const device='device_12345',folder={id:'folder_12345',name:'Our Home'},own={id:'own_file_123',name:'Mine'},partner={id:'partner_12345',name:'Partner'};
function memory(){const data=new Map();return {getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key),data}}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
function fixture(storage=memory()){
  const calls=[],journals=new Map();let activations=0;
  const binding=id=>({fileId:id,deviceId:device,conditionalVerified:true});
  const transport={request:async()=>{calls.push('folder');return folder},createJournal:async()=>{calls.push('own');journals.set(own.id,{writer:device,operations:[]});return own},createPartnerSlot:async()=>{calls.push('partner');journals.set(partner.id,{writer:'unclaimed',operations:[]});return partner},resumeClaim:async(token,id)=>{calls.push('verify:'+id);if(journals.get(id)?.writer!==device||journals.get(id)?.operations.length)throw new SyncError('Cannot adopt this file');return binding(id)},readJournal:async(token,id)=>{calls.push('read:'+id);return {journal:journals.get(id)}},claimSlot:async(token,id)=>{calls.push('claim:'+id);if(journals.get(id)?.writer!=='unclaimed')throw new SyncError('Already assigned');journals.set(id,{writer:device,operations:[]});return binding(id)}};
  const activate=async(...args)=>{calls.push('activate');activations++;return args};
  const make=(options={})=>new HouseholdSetup({transport,localStorage:storage,storageKey:'setup',device,activate,locks:null,...options});
  return {storage,calls,journals,transport,make,setup:make(),activations:()=>activations};
}
test('create records confirmed steps, activates last and never persists tokens',async()=>{
  const f=fixture();const result=await f.setup.create('SECRET_TOKEN',{name:'Our Home',deviceName:'Phone'});
  assert.deepEqual(f.calls,['folder','own','verify:'+own.id,'partner','activate']);assert.equal(result.binding.fileId,own.id);assert.equal(f.setup.state(),null);assert.equal(f.storage.getItem('setup'),null);
});
test('stop during a create keeps confirmed ID and makes no follow-on requests',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();f.transport.request=async()=>{f.calls.push('folder');entered.resolve();return pending.promise};
  const running=f.setup.create('SECRET_TOKEN',{name:'Our Home'});await entered.promise;f.setup.stop();pending.resolve(folder);
  await assert.rejects(running,error=>error.status===499);assert.deepEqual(f.calls,['folder']);assert.equal(f.setup.state().folder.id,folder.id);assert.equal(f.setup.state().step,'own');assert.equal(f.storage.getItem('setup').includes('SECRET_TOKEN'),false);
  await f.setup.resume('fresh_token');assert.equal(f.calls.filter(c=>c==='folder').length,1);assert.equal(f.activations(),1);
});
test('reload resumes known own file verification without creating a duplicate',async()=>{
  const f=fixture();let once=true;f.transport.resumeClaim=async(token,id)=>{f.calls.push('verify:'+id);if(once){once=false;throw new Error('offline')}return {fileId:id,deviceId:device,conditionalVerified:true}};
  await assert.rejects(f.setup.create('secret',{name:'Our Home'}),/offline/);assert.equal(f.setup.state().own.id,own.id);
  const restarted=f.make();await restarted.resume('fresh');assert.equal(f.calls.filter(c=>c==='folder').length,1);assert.equal(f.calls.filter(c=>c==='own').length,1);assert.equal(f.activations(),1);
});
test('uncertain create outcome is never automatically repeated',async()=>{
  const f=fixture();f.transport.createPartnerSlot=async()=>{f.calls.push('partner');throw new Error('Lost response after send')};
  await assert.rejects(f.setup.create('secret',{name:'Our Home'}),/Lost response/);assert.equal(f.setup.state().inflight,'partner');
  const restarted=f.make();await assert.rejects(restarted.resume('fresh'),/unconfirmed/);assert.equal(f.calls.filter(c=>c==='partner').length,1);assert.equal(f.activations(),0);
});
test('explicit refused creation can be retried after reconnecting',async()=>{
  const f=fixture();let once=true;f.transport.request=async()=>{f.calls.push('folder');if(once){once=false;throw new SyncError('expired',401)}return folder};
  await assert.rejects(f.setup.create('secret',{name:'Home'}),error=>error.status===401);assert.equal(f.setup.state().inflight,null);await f.setup.resume('new');assert.equal(f.activations(),1);
});
test('lost successful claim response reconciles exact owned empty slot after reload',async()=>{
  const f=fixture();f.journals.set(partner.id,{writer:'unclaimed',operations:[]});f.transport.claimSlot=async(token,id)=>{f.calls.push('claim:'+id);f.journals.set(id,{writer:device,operations:[]});throw new Error('Claim response lost')};
  await assert.rejects(f.setup.join('secret',{folder,files:[own,partner],slotId:partner.id}),/lost/);assert.equal(f.setup.state().inflight,'claim');
  await f.make().resume('fresh');assert.equal(f.calls.filter(c=>c==='claim:'+partner.id).length,1);assert.ok(f.calls.includes('verify:'+partner.id));assert.equal(f.activations(),1);
});
test('resume refuses another writer or populated claimed file',async()=>{
  for(const journal of [{writer:'another_device',operations:[]},{writer:device,operations:[{}]}]){
    const f=fixture();f.journals.set(partner.id,journal);await assert.rejects(f.setup.join('secret',{folder,files:[own,partner],slotId:partner.id}));assert.equal(f.activations(),0);assert.equal(f.calls.some(c=>c.startsWith('claim:')),false);
  }
});
test('activation failure retains binding and does not repeat successful remote writes',async()=>{
  const f=fixture();let once=true;const activate=async()=>{f.calls.push('activate');if(once){once=false;throw new Error('Local configuration failed')}};const setup=f.make({activate});
  await assert.rejects(setup.create('secret',{name:'Home'}),/configuration/);assert.equal(setup.state().binding.fileId,own.id);assert.equal(setup.state().step,'activate');await f.make({activate}).resume('fresh');assert.equal(f.calls.filter(c=>c==='own').length,1);assert.equal(f.calls.filter(c=>c==='partner').length,1);assert.equal(f.calls.filter(c=>c==='activate').length,2);
});
test('abandon does not delete remote resources or resurrect pending state on late response',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();f.transport.request=async()=>{f.calls.push('folder');entered.resolve();return pending.promise};const running=f.setup.create('secret',{name:'Home'});await entered.promise;
  const previous=f.setup.abandon();assert.equal(previous.inflight,'folder');pending.resolve(folder);await assert.rejects(running,error=>error.status===499);assert.equal(f.setup.state(),null);assert.equal(f.storage.getItem('setup'),null);assert.deepEqual(f.calls,['folder']);
});
test('repeated start is blocked while pending progress exists',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();f.transport.request=async()=>{entered.resolve();return pending.promise};const running=f.setup.create('secret',{name:'Home'});await entered.promise;
  assert.throws(()=>f.setup.create('secret',{name:'Duplicate'}),/already exists/);await assert.rejects(f.setup.resume('secret'),/already running/);f.setup.stop();pending.resolve(folder);await assert.rejects(running,error=>error.status===499);
});
test('local storage failure before request performs no external mutation',async()=>{
  const f=fixture();f.storage.setItem=()=>{throw new Error('Storage full')};assert.throws(()=>f.setup.create('secret',{name:'Home'}),/Storage full/);assert.deepEqual(f.calls,[]);
});
test('activation receives cancellation control and pending survives stop',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();let control;const setup=f.make({activate:async(a,b,c,options)=>{control=options;entered.resolve();await pending.promise}});
  const running=setup.create('secret',{name:'Home'});await entered.promise;setup.stop();assert.equal(control.isActive(),false);pending.resolve();await assert.rejects(running,error=>error.status===499);assert.equal(setup.state().step,'done');await setup.resume('fresh');assert.equal(setup.state(),null);
});
test('extra-device add is durable and never creates another folder or partner slot',async()=>{
  const f=fixture();await f.setup.add('secret',{folder,deviceName:'Tablet'});assert.deepEqual(f.calls,['own','verify:'+own.id,'activate']);assert.equal(f.setup.state(),null);
});
test('paused activation after local configuration resumes without reprobe or duplicate resources',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();let configured=false,started=0;
  const activate=async(a,b,c,control)=>{configured=true;entered.resolve();await pending.promise;if(!control.isActive())throw new SyncError('stopped',499);started++};
  const setup=f.make({activate}),running=setup.add('secret',{folder});await entered.promise;setup.stop();pending.resolve();await assert.rejects(running,error=>error.status===499);
  assert.equal(configured,true);assert.equal(started,0);assert.equal(setup.state().step,'activate');f.journals.set(own.id,{writer:device,operations:[{already:'uploaded'}]});
  await setup.resume('fresh');assert.equal(started,1);assert.equal(f.calls.filter(c=>c==='own').length,1);assert.equal(f.calls.filter(c=>c.startsWith('verify:')).length,1);assert.equal(setup.state(),null);
});
test('another window cannot overwrite pending setup based on a stale empty view',async()=>{
  const f=fixture(),other=f.make(),pending=deferred(),entered=deferred();assert.equal(other.state(),null);
  f.transport.request=async()=>{entered.resolve();return pending.promise};const running=f.setup.create('secret',{name:'First'});await entered.promise;
  assert.throws(()=>other.create('secret',{name:'Second'}),/already exists/);f.setup.stop();pending.resolve(folder);await assert.rejects(running,error=>error.status===499);
});
test('cross-window abandon cannot be resurrected by a late creation response',async()=>{
  const f=fixture(),pending=deferred(),entered=deferred();f.transport.request=async()=>{entered.resolve();return pending.promise};const running=f.setup.create('secret',{name:'Home'});await entered.promise;
  f.make().abandon();pending.resolve(folder);await assert.rejects(running,error=>error.status===499);assert.equal(f.setup.state(),null);
});
test('setup uses a cross-window lock and refuses unsafe saved state',async()=>{
  const f=fixture();const locked=f.make({locks:{request:async(name,options,callback)=>{assert.match(name,/household-setup/);assert.equal(options.ifAvailable,true);return callback(null)}}});
  await assert.rejects(locked.add('secret',{folder}),/another window/);assert.deepEqual(f.calls,[]);
  f.storage.setItem('setup',JSON.stringify({...locked.state(),token:'must-not-be-restored'}));assert.throws(()=>f.make().state(),/invalid fields/);
});
