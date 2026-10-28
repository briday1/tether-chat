import test from 'node:test';import assert from 'node:assert/strict';
import {DriveJournals} from '../../tend/drive-journals.mjs';
import {makeChanges} from '../../tend/drive-sync-core.mjs';
const when='2026-10-28T00:00:00Z',workspace='workspace_123',device='device_12345',file='journal_12345',peerFile='journal_99999';
const task={id:'task1',title:'Milk',summary:'',state:'open',categories:['Home'],revisit_at:null,due_at:null,recurrence:null,next_occurrence:null,archived_at:null,created_at:when,updated_at:when};
const records={'task:task1':task},start=makeChanges([],{},records,device,'operation_0001',when);
const session={mode:'selected-journals',workspaceId:workspace,files:[{id:file,name:'mine'},{id:peerFile,name:'peer'}]};
const envelope=(writer=device,operations=[])=>({format:'tether-home-journal',version:1,workspace,writer,operations});
const response=(data,status=200,etag='"revision1"')=>new Response(JSON.stringify(data),{status,headers:{...(etag?{ETag:etag}:{}),'Content-Type':'application/json'}});
function fixture(){const requests=[],remote=new Map([[file,envelope()],[peerFile,envelope('device_peer1')]]);const fetcher=async(url,options)=>{
  requests.push({url,options});const id=new URL(url).pathname.split('/').at(-1);
  if(options.method==='PATCH'){remote.set(id,JSON.parse(options.body));return response({id},200)}
  return response(remote.get(id),200);
};return {requests,remote,fetcher,transport:new DriveJournals({fileId:file,deviceId:device,conditionalVerified:true,fetcher})}}

test('pull reads only explicitly selected files and never discovers folders',async()=>{
  const f=fixture();f.remote.set(peerFile,envelope('device_peer1',[start]));const result=await f.transport.pull('secret',session);
  assert.deepEqual(result,[start]);assert.equal(f.requests.length,2);assert.ok(f.requests.every(r=>r.url.includes('?alt=media')&&!r.url.includes('q=')));assert.ok(f.requests.every(r=>r.options.headers.Authorization==='Bearer secret'&&r.options.credentials==='omit'&&r.options.redirect==='error'));
});
test('push merges all immutable operations into only its own writer journal',async()=>{
  const f=fixture();const other=structuredClone(records);other['task:task1'].summary='Peer edit';const peer=makeChanges([start],records,other,'device_peer1','operation_0002',when);
  f.remote.set(file,envelope(device,[start]));const done=await f.transport.push('secret',session,[peer,start],'different_actor',[]);
  assert.equal(done.length,2);const patch=f.requests.find(r=>r.options.method==='PATCH');assert.match(patch.url,new RegExp(file));assert.equal(patch.options.headers['If-Match'],'"revision1"');assert.equal(f.remote.get(file).operations.length,2);assert.equal(f.remote.get(peerFile).operations.length,0);
});
test('unbound/imported state cannot turn a peer journal into this device writer',async()=>{
  let count=0;const transport=new DriveJournals({fetcher:async()=>{count++;return response(envelope())}});
  await assert.rejects(transport.push('secret',session,[start],device,[]),/read-only/);assert.equal(count,0);
  const f=fixture();f.remote.set(file,envelope('device_peer1'));
  await assert.rejects(f.transport.push('secret',session,[start],device,[]),/another device/);assert.equal(f.requests.length,1);
});
test('own binding must remain explicitly selected',async()=>{
  const f=fixture();await assert.rejects(f.transport.push('secret',{...session,files:[{id:peerFile}]},[start],device,[]),/own journal/);assert.equal(f.requests.length,0);
});
test('missing or weak accessible ETag prevents any media replacement',async()=>{
  for(const etag of ['', 'W/"weak"','raw-etag']){let calls=0;const transport=new DriveJournals({fileId:file,deviceId:device,conditionalVerified:true,fetcher:async()=>{calls++;return response(envelope(),200,etag)}});
    await assert.rejects(transport.push('secret',session,[start],device,[]),/ETag/);assert.equal(calls,1);
  }
});
test('HTTP 412 propagates without claiming uploaded operations',async()=>{
  let calls=0;const transport=new DriveJournals({fileId:file,deviceId:device,conditionalVerified:true,fetcher:async()=>++calls===1?response(envelope()):response({},412)});
  await assert.rejects(transport.push('secret',session,[start],device,[]),error=>error.status===412);assert.equal(calls,2);
});
test('uncertain patch is not acknowledged and next pull/retry avoids replacement',async()=>{
  let stored=envelope(),calls=0,patches=0;const transport=new DriveJournals({fileId:file,deviceId:device,conditionalVerified:true,fetcher:async(url,options)=>{calls++;if(options.method==='PATCH'){patches++;stored=JSON.parse(options.body);throw new Error('Network ended after send')}return response(stored)}});
  await assert.rejects(transport.push('secret',session,[start],device,[]),/Network/);
  const done=await transport.push('secret',session,[start],device,[]);assert.deepEqual(done,[start.id]);assert.equal(patches,1);assert.equal(calls,3);
});
test('bad envelopes, wrong workspaces and corrupt operations fail closed',async()=>{
  for(const bad of [{...envelope(),workspace:'other_workspace'}, {...envelope(),version:2}, {...envelope(),writer:''}, {...envelope(),api_key:'secret'}, {...envelope(),operations:[{bad:true}]}]){
    const transport=new DriveJournals({fetcher:async()=>response(bad)});await assert.rejects(transport.pull('secret',{...session,files:[{id:file}]}));
  }
});
test('bounded response fails before parsing a huge journal',async()=>{
  const transport=new DriveJournals({fetcher:async()=>new Response('{}',{headers:{'Content-Length':String(9*1024*1024)}})});
  await assert.rejects(transport.pull('secret',{...session,files:[{id:file}]}),/8 MB/);
});
test('stop prevents further selected-file requests and uploads',async()=>{
  let running=true,calls=0;const transport=new DriveJournals({fileId:file,deviceId:device,conditionalVerified:true,fetcher:async()=>{calls++;running=false;return response(envelope())}});
  await assert.rejects(transport.pull('secret',session,{isActive:()=>running}),error=>error.status===499);assert.equal(calls,1);
  await assert.rejects(transport.push('secret',session,[start],device,[],{isActive:()=>false}),error=>error.status===499);assert.equal(calls,1);
});
test('explicit create returns a binding candidate but never adopts it automatically',async()=>{
  const f=fixture();let created;f.transport.create=async(token,folder,name,data)=>{created={token,folder,name,data};return {id:'new_journal_123',name}};
  const result=await f.transport.createJournal('secret','folder_12345',workspace,device);assert.equal(result.id,'new_journal_123');assert.equal(f.transport.binding.fileId,file);assert.equal(created.data.format,'tether-home-journal');assert.deepEqual(created.data.operations,[]);assert.equal(created.data.writer,device);
});
async function probeFixture({etag='"revision1"',patchStatus=412,journal=envelope()}={}){
  const requests=[];const transport=new DriveJournals({fetcher:async(url,options)=>{requests.push({url,options});return options.method==='PATCH'?response({},patchStatus):response(journal,200,etag)}});
  transport.create=async()=>({id:file,name:'new'});await transport.createJournal('secret','folder_12345',workspace,device);
  return {transport,requests};
}
test('empty-new-journal probe requires server to reject intentionally wrong ETag',async()=>{
  const f=await probeFixture();const result=await f.transport.verifyConditionalWrites('secret',file,workspace,device);
  assert.equal(result.conditionalVerified,true);assert.equal(f.requests.length,2);const patch=f.requests[1];assert.notEqual(patch.options.headers['If-Match'],'"revision1"');assert.match(patch.options.headers['If-Match'],/^"tether-precondition-probe-/);assert.deepEqual(JSON.parse(patch.options.body).operations,[]);
  assert.equal(f.transport.binding,null); // Only UI can persist a verified writer binding.
});
test('server ignoring If-Match is detected and blocked before task publication',async()=>{
  const f=await probeFixture({patchStatus:200});await assert.rejects(f.transport.verifyConditionalWrites('secret',file,workspace,device),/did not enforce/);
  assert.deepEqual(JSON.parse(f.requests[1].options.body).operations,[]);
});
test('probe refuses existing or nonempty journals and inaccessible ETag',async()=>{
  const f=fixture();await assert.rejects(f.transport.verifyConditionalWrites('secret',file,workspace,device),/just created/);assert.equal(f.requests.length,0);
  for(const options of [{journal:envelope(device,[start])},{journal:envelope('device_peer1')},{etag:''},{etag:'W/"revision"'}]){
    const p=await probeFixture(options);await assert.rejects(p.transport.verifyConditionalWrites('secret',file,workspace,device));assert.equal(p.requests.length,1);
  }
});
test('old binding without explicit successful capability verification cannot push',async()=>{
  const f=fixture();delete f.transport.binding.conditionalVerified;await assert.rejects(f.transport.push('secret',session,[start],device,[]),/not verified/);assert.equal(f.requests.length,0);
});
