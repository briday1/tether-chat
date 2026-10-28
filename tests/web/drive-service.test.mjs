import test from 'node:test';
import assert from 'node:assert/strict';
import {HomeSync} from '../../tether/drive-sync-service.mjs';
import {makeChanges,mergeJournal,stable,SyncError} from '../../tether/drive-sync-core.mjs';
const when='2026-10-28T00:00:00Z';
const task={id:'task1',title:'Milk',summary:'',state:'open',categories:['Home'],revisit_at:null,due_at:null,recurrence:null,next_occurrence:null,archived_at:null,created_at:when,updated_at:when};
const records={'task:task1':task},session={mode:'folder-records',folderId:'folder_12345',workspaceId:'space_12345'};
const clone=v=>structuredClone(v);
function localStore(initial=records){
  let state={records:clone(initial),metadata:{},revision:0};
  return {read:()=>clone(state),edit:fn=>fn(state.records),local:async(method,body)=>{
    if(method==='GET')return clone(state);
    if(body.expected_revision!==state.revision||stable(body.expected)!==stable(state.records))throw new SyncError('changed',409);
    state={records:clone(body.records),metadata:clone(body.metadata),revision:state.revision+1};return clone(state);
  }};
}
function fixture(initial=records){
  const store=localStore(initial),remote=[];let calls=[];
  const transport={pull:async()=>{calls.push('pull');return clone(remote)},push:async(token,settings,log,actor,uploaded)=>{calls.push('push');const ops=log.filter(op=>op.actor===actor&&!uploaded.includes(op.id));remote.splice(0,remote.length,...mergeJournal(remote,ops));return ops.map(op=>op.id)}};
  const service=new HomeSync({local:store.local,transport,actor:'device_12345',locks:null});service.token='token';
  return {store,remote,calls,transport,service};
}
async function configure(f){await f.service.configure(session,{publishExisting:true})}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}

test('initial Home publication requires confirmation and only commits local config',async()=>{
  const f=fixture();await assert.rejects(f.service.configure(session),/Confirm/);assert.deepEqual(f.store.read().metadata,{});
  await configure(f);assert.deepEqual(f.calls,[]);assert.equal(f.store.read().records['task:task1'].title,'Milk');
});
test('offline changes are durable before network and retry uploads once',async()=>{
  const f=fixture();await configure(f);let captured;
  f.transport.pull=async()=>{captured=f.store.read();throw new SyncError('offline',503)};
  await assert.rejects(f.service.sync(),/offline/);assert.equal(captured.metadata.log.length,1);assert.equal(captured.metadata.baseline['task:task1'].title,'Milk');assert.equal(f.store.read().metadata.uploaded.length,0);
  f.transport.pull=async()=>[];await f.service.sync();assert.equal(f.remote.length,1);assert.equal(f.store.read().metadata.log.length,1);assert.equal(f.store.read().metadata.uploaded.length,1);
  await f.service.sync();assert.equal(f.remote.length,1);
});
test('offline operations survive a new controller actor after restart',async()=>{
  const f=fixture();await configure(f);f.transport.pull=async()=>{throw new SyncError('offline',503)};await assert.rejects(f.service.sync());
  f.transport.pull=async()=>[];const restarted=new HomeSync({local:f.store.local,transport:f.transport,actor:'device_99999',locks:null});restarted.token='newtoken';await restarted.sync();
  assert.equal(f.remote.length,1);assert.equal(f.store.read().metadata.uploaded.length,1);
});
test('edit during pull triggers CAS and survives the next retry',async()=>{
  const f=fixture();await configure(f);await f.service.sync();
  f.transport.pull=async()=>{f.store.edit(rows=>rows['task:task1'].summary='Edited while pulling');return clone(f.remote)};
  await assert.rejects(f.service.sync(),error=>error.status===409);assert.equal(f.store.read().records['task:task1'].summary,'Edited while pulling');
  f.transport.pull=async()=>clone(f.remote);await f.service.sync();assert.equal(f.store.read().records['task:task1'].summary,'Edited while pulling');assert.equal(f.remote.length,2);
});
test('edit during upload is not overwritten or marked captured prematurely',async()=>{
  const f=fixture();await configure(f);const original=f.transport.push;
  f.transport.push=async(...args)=>{const ids=await original(...args);f.store.edit(rows=>rows['task:task1'].summary='Edited during upload');return ids};
  await f.service.sync();assert.equal(f.store.read().records['task:task1'].summary,'Edited during upload');assert.equal(f.store.read().metadata.baseline['task:task1'].summary,'');
  f.transport.push=original;await f.service.sync();assert.equal(f.remote.length,2);assert.equal(f.store.read().metadata.baseline['task:task1'].summary,'Edited during upload');
});
test('expired authorization clears credentials but retains queued edits',async()=>{
  const f=fixture();await configure(f);f.transport.pull=async()=>{throw new SyncError('expired',401)};
  await assert.rejects(f.service.sync(),error=>error.status===401);assert.equal(f.service.token,'');assert.equal(f.store.read().metadata.log.length,1);assert.match(f.service.status,/Reconnect/);
});
test('disconnect during pull prevents later push, state resurrection and Synced status',async()=>{
  const f=fixture();await configure(f);const pending=deferred(),entered=deferred();
  f.transport.pull=async()=>{entered.resolve();return pending.promise};const run=f.service.sync();await entered.promise;
  await f.service.disconnect();pending.resolve([]);await run;
  assert.ok(f.store.read().metadata.detached);assert.equal(f.store.read().metadata.session,undefined);assert.equal(f.remote.length,0);assert.equal(f.service.token,'');assert.match(f.service.status,/Disconnected/);
});
test('disconnect during upload cannot resurrect local sync metadata',async()=>{
  const f=fixture();await configure(f);const pending=deferred(),entered=deferred();
  f.transport.push=async()=>{entered.resolve();return pending.promise};const run=f.service.sync();await entered.promise;
  await f.service.disconnect();pending.resolve(['already_in_flight']);await run;
  assert.ok(f.store.read().metadata.detached);assert.equal(f.store.read().metadata.session,undefined);assert.match(f.service.status,/Disconnected/);
});
test('resolving remote conflict preserves unrelated unsynced local edits',async()=>{
  const f=fixture();await configure(f);await f.service.sync();const root=f.remote[0];
  const a=clone(records),b=clone(records);a['task:task1'].title='Bread';b['task:task1'].title='Eggs';
  f.remote.push(makeChanges([root],records,a,'device_other1','operation_1001',when),makeChanges([root],records,b,'device_other2','operation_1002',when));
  await f.service.sync();assert.equal(f.store.read().metadata.conflicts.length,1);
  f.store.edit(rows=>rows['task:task1'].summary='Never lose this local edit');
  await f.service.choose('task:task1','title','Eggs');
  assert.equal(f.store.read().records['task:task1'].title,'Eggs');assert.equal(f.store.read().records['task:task1'].summary,'Never lose this local edit');
});
test('uncertain upload replay is idempotent after remote copy is pulled',async()=>{
  const f=fixture();await configure(f);const original=f.transport.push;let once=true;
  f.transport.push=async(...args)=>{const ids=await original(...args);if(once){once=false;throw new SyncError('timeout',503)}return ids};
  await assert.rejects(f.service.sync(),/timeout/);assert.equal(f.remote.length,1);assert.equal(f.store.read().metadata.uploaded.length,0);
  await f.service.sync();assert.equal(f.remote.length,1);assert.equal(f.store.read().metadata.uploaded.length,1);
});
test('a second controller disconnect during upload does not restore shared settings',async()=>{
  const f=fixture();await configure(f);const pending=deferred(),entered=deferred();
  f.transport.push=async()=>{entered.resolve();return pending.promise};const run=f.service.sync();await entered.promise;
  const other=new HomeSync({local:f.store.local,transport:f.transport,actor:'device_other1',locks:null});await other.disconnect();pending.resolve(['sent_before_disconnect']);await run;
  assert.ok(f.store.read().metadata.detached);assert.equal(f.store.read().metadata.session,undefined);
});
test('stop exposes inactive state to transport and prevents further commits',async()=>{
  const f=fixture();await configure(f);const pending=deferred(),entered=deferred();let control;
  f.transport.pull=async(token,settings,options)=>{control=options;entered.resolve();return pending.promise};const run=f.service.sync();await entered.promise;
  assert.equal(control.isActive(),true);f.service.stop();assert.equal(control.isActive(),false);const before=f.store.read();pending.resolve([]);await run;assert.deepEqual(f.store.read(),before);
});
test('deletion while disconnected resumes as a tombstone instead of resurrection',async()=>{
  const f=fixture();await configure(f);await f.service.sync();const firstConnection=f.store.read().metadata.connection;
  await f.service.disconnect();assert.equal(f.store.read().metadata.session,undefined);assert.equal(f.store.read().metadata.detached.log.length,1);
  f.store.edit(rows=>delete rows['task:task1']);await assert.rejects(f.service.configure(session),/Confirm/);
  await configure(f);assert.notEqual(f.store.read().metadata.connection,firstConnection);assert.equal(f.store.read().metadata.detached,undefined);
  f.service.token='reconnected';await f.service.sync();assert.deepEqual(f.store.read().records,{});assert.equal(f.remote.length,2);assert.ok(f.remote.some(op=>op.changes.some(change=>change.key==='task:task1'&&change.field==='$exists'&&change.value===false)));
});
test('a different shared workspace starts a new journal without old operations',async()=>{
  const f=fixture();await configure(f);await f.service.sync();const priorIds=f.store.read().metadata.log.map(op=>op.id);
  await f.service.disconnect();f.store.edit(rows=>rows['task:task1'].title='Only current visible content');
  const other={...session,workspaceId:'different_space',folderId:'different_folder'};
  await f.service.configure(other,{publishExisting:true});assert.deepEqual(f.store.read().metadata.log,[]);assert.deepEqual(f.store.read().metadata.baseline,{});assert.equal(f.store.read().metadata.detached,undefined);
  f.remote.splice(0);f.service.token='newtoken';await f.service.sync();assert.equal(f.remote.length,1);assert.ok(f.remote.every(op=>!priorIds.includes(op.id)));assert.equal(f.store.read().records['task:task1'].title,'Only current visible content');
});
test('disconnect stays idempotent and excludes tokens and nested metadata',async()=>{
  const f=fixture();await configure(f);await f.service.sync();let state=await f.store.local('GET');
  await f.store.local('POST',{expected:state.records,records:state.records,expected_revision:state.revision,metadata:{...state.metadata,token:'secret',session:{...session,access_token:'secret'},detached:{detached:{bad:true}}}});
  await f.service.disconnect();const once=f.store.read().metadata;await f.service.disconnect();assert.deepEqual(f.store.read().metadata,once);assert.equal(JSON.stringify(once).includes('secret'),false);assert.equal(once.detached.detached,undefined);assert.equal(once.connection,undefined);
});
test('same-workspace reconnection keeps previously selected peer files',async()=>{
  const f=fixture();const old={...session,mode:'selected-journals',files:[{id:'own_file_123',name:'Mine'},{id:'peer_file_123',name:'Spouse'}]};
  await f.service.configure(old,{publishExisting:true});await f.service.disconnect();
  await f.service.configure({...old,files:[{id:'own_file_123',name:'Mine again'}]},{publishExisting:true});
  assert.deepEqual(f.store.read().metadata.session.files,[{id:'own_file_123',name:'Mine again'},{id:'peer_file_123',name:'Spouse'}]);
});
