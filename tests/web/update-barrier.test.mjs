import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';
const source=fs.readFileSync(new URL('../../web/update.html',import.meta.url),'utf8');
const helpers=source.slice(source.indexOf('    async function databaseBusy'),source.indexOf("    const expected=document.querySelector"));
function setup(states,{blocked}={}){
 const opens=[],modes=[],held=[],locks=[];
 const indexedDB={open(name){opens.push(name);const request={};queueMicrotask(()=>{
  if(!(name in states)){request.transaction={abort(){request.onerror()}};request.onupgradeneeded();return}
  request.result={objectStoreNames:{contains:()=>true},close(){},transaction(store,mode){modes.push(mode);const tx={objectStore(){return {get(){const read={result:{jobs:states[name]}};queueMicrotask(()=>{read.onsuccess();tx.oncomplete()});return read}}}};return tx}};request.onsuccess();
 });return request}};
 const navigator={locks:{async request(name,options,fn){locks.push(name);if(name===blocked)return fn(null);held.push(name);try{return await fn({name})}finally{held.pop()}}}};
 const context={base:{pathname:'/app/'},indexedDB,navigator,Promise,Date};vm.createContext(context);vm.runInContext(helpers+'\nthis.busy=busy;this.withQueueLocks=withQueueLocks;',context);return {...context,opens,modes,held,locks};
}
const work='tether-chat-web:/app/',home=work+':home',recent={status:'running',updated_at:new Date().toISOString()};
test('update checks both legacy Work and current Home without creating absent databases',async()=>{
 for(const db of [work,home]){const f=setup({[db]:[recent]});assert.equal(await f.busy(),true);assert.deepEqual(f.opens.sort(),[work,home].sort());assert.deepEqual(f.modes,['readonly'])}
 assert.equal(await setup({}).busy(),false);
});
test('update preserves recent120second bound',async()=>{
 const old={status:'queued',updated_at:new Date(Date.now()-121000).toISOString()};assert.equal(await setup({[work]:[old],[home]:[{status:'done',updated_at:recent.updated_at}]}).busy(),false);
});
test('both queue locks remain held throughout update',async()=>{
 const f=setup({[home]:[]});let ran=false;assert.equal(await f.withQueueLocks(async()=>{ran=true;assert.deepEqual(f.held,['tether-chat-web-queue:/app/','tether-chat-web-queue:/app/:home'])}),true);assert.equal(ran,true);assert.deepEqual(f.held,[]);
});
test('busy old or new queue prevents update',async()=>{
 for(const blocked of ['tether-chat-web-queue:/app/','tether-chat-web-queue:/app/:home']){const f=setup({},{blocked});let ran=false;assert.equal(await f.withQueueLocks(()=>{ran=true}),false);assert.equal(ran,false)}
 const f=setup({[home]:[recent]});assert.equal(await f.withQueueLocks(()=>{throw Error('must not run')}),false);
});
