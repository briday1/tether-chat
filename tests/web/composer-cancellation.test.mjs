import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../tether/chat.js',import.meta.url),'utf8');
const helpers=source.slice(source.indexOf(' const sendPromises='),source.indexOf(' stopButton.onclick='));
function setup({job=true,outbox=false,fetch}={}){
 const storage=new Map(),journal=outbox?{'request-001':{request_id:'request-001',text:'Original'}}:{},send={};
 const button=()=>({setAttribute(name,value){this[name]=value},focus(){context.document.activeElement=this}});
 const input={value:''};
 const context={stopKey:'stops',stopping:false,submitting:false,window:{addEventListener(){}},jobs:job?[{id:'request-001',status:'running'}]:[],stopButton:button(),interruptButton:button(),document:{querySelector:s=>s==='#message'?input:send},
  localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},readJournal:()=>journal,remember:p=>journal[p.request_id]=p,forget:id=>delete journal[id],sync:async()=>{},fetch};
 vm.createContext(context);vm.runInContext(helpers,context);send.focus=()=>context.document.activeElement=send;return {context,journal,storage,input,send,run:code=>vm.runInContext(code,context)};
}
test('Stop posts an atomic stopped outbox without awaiting the original pending send',async()=>{
 const calls=[];const state=setup({outbox:true,fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:true,json:async()=>({id:'request-001',status:'interrupted'})}}});
 state.run("sendPromises.set('request-001',new Promise(()=>{}))");
 assert.equal(await state.run('stopActive()'),'request-001');assert.equal(calls.length,2);assert.equal(calls[0].body.stop_requested,true);
 assert.equal(Object.keys(state.journal).length,0);assert.equal(state.storage.get('stops'),'{}');assert.equal(state.context.stopping,false);
});
test('offline Stop retains explicit cancellation intent and draft-independent outbox flag',async()=>{
 const state=setup({outbox:true,fetch:async()=>{throw Error('offline')}});
 await assert.rejects(state.run('stopActive()'),/offline/);assert.equal(state.journal['request-001'].stop_requested,true);assert.equal(JSON.parse(state.storage.get('stops'))['request-001'],true);assert.equal(state.context.stopping,false);
});
test('accepted offline Stop survives reload and retries only the explicitly stopped job',async()=>{
 let online=false,calls=0;const state=setup({fetch:async()=>{calls++;if(!online)throw Error('offline');return {ok:true,json:async()=>({id:'request-001',status:'interrupted'})}}});
 await assert.rejects(state.run('stopActive()'));online=true;state.run('retryStops()');
 for(let i=0;i<10;i++)await Promise.resolve();assert.equal(calls,2);assert.equal(state.storage.get('stops'),'{}');assert.equal(state.context.jobs[0].status,'interrupted');
});
test('a reloaded accepted Stop blocks continuation until cancellation is confirmed even before state loads',async()=>{
 let calls=0;const state=setup({job:false,outbox:false,fetch:async()=>{calls++;throw Error('offline')}});
 state.storage.set('stops',JSON.stringify({'request-001':true}));assert.equal(state.run('activeIds().length'),1);
 await assert.rejects(state.run('stopActive()'),/offline/);assert.equal(calls,1);assert.equal(JSON.parse(state.storage.get('stops'))['request-001'],true);
});

test('send and Stop exchange one slot; added context exposes interrupt without hiding Stop',()=>{
 const state=setup();state.run('updateControls()');assert.equal(state.send.hidden,true);assert.equal(state.context.stopButton.hidden,false);assert.equal(state.context.interruptButton.hidden,true);
 state.input.value='Added context';state.run('updateControls()');assert.equal(state.context.stopButton.hidden,false);assert.equal(state.context.interruptButton.hidden,false);
 state.context.stopping=true;state.run('updateControls()');assert.equal(state.context.stopButton.disabled,true);assert.equal(state.context.interruptButton.disabled,true);assert.equal(state.context.stopButton['aria-busy'],'true');
 state.context.stopping=false;state.context.jobs=[];state.run('updateControls()');assert.equal(state.send.hidden,false);assert.equal(state.context.stopButton.hidden,true);assert.equal(state.context.interruptButton.hidden,true);
});
test('keyboard focus follows the same action slot and dictation cannot submit an interrupt',()=>{
 const state=setup();state.context.document.activeElement=state.send;state.run('updateControls()');assert.equal(state.context.document.activeElement,state.context.stopButton);
 state.input.value='Context';state.send.disabled=true;state.run('updateControls()');assert.equal(state.context.interruptButton.disabled,true);assert.equal(state.context.stopButton.disabled,false);
 state.context.jobs=[];state.run('updateControls()');assert.equal(state.context.document.activeElement,state.send);
});
