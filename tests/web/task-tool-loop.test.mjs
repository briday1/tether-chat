import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyState,Model,copy} from '../../web/store.mjs';
import {createRuntime} from '../../web/runtime.mjs';

class MemoryDB {
  constructor(){this.state=emptyState()}
  async read(fn){return copy(fn(copy(this.state)))}
  async write(fn){const candidate=copy(this.state),result=fn(candidate);this.state=candidate;return copy(result)}
}
class Locks {
  busy=false;
  async request(name,options,fn){if(this.busy)return fn(null);this.busy=true;try{return await fn({name})}finally{this.busy=false}}
}
const response=message=>Response.json({choices:[{message}]});
const tool=(name,args,id)=>response({content:null,tool_calls:[{id,type:'function',function:{name,arguments:JSON.stringify(args)}}]});
const lastTool=body=>JSON.parse(body.messages.filter(message=>message.role==='tool').at(-1).content);
async function waitFor(check){for(let i=0;i<300;i++){const value=check();if(value)return value;await new Promise(resolve=>setTimeout(resolve,5))}throw Error('Queue did not finish')}

async function setup(t,respond) {
  const db=new MemoryDB(),requests=[];
  const config={base:'/tool-check/',origin:'https://tether.test',version:'test',system:'Use tools.',tools:
    [['get_context',[]],['defer_task',['id','when']],['search_history',['query']]].map(([name,required])=>({type:'function',function:{name,parameters:{type:'object',required}}}))};
  const runtime=await createRuntime({config,db,locks:new Locks(),session:{getItem(){return null},setItem(){},removeItem(){}},network:async(url,options)=>{
    assert.equal(url,'https://provider.test/v1/chat/completions');
    const body=JSON.parse(options.body);requests.push(body);return respond(body,requests.length,db);
  }});
  t.after(()=>runtime.close());
  const api=async(path,body)=>{
    const result=await runtime.fetch(config.origin+config.base+'api'+path,{method:'POST',body:JSON.stringify(body)});
    return {status:result.status,data:await result.json()};
  };
  assert.equal((await api('/settings',{base_url:'https://provider.test/v1',model:'tool-model',api_key:'synthetic-key',remember:false})).status,200);
  return {db,api,requests};
}

test('repeated context reads see manual edits made during the provider turn',async t=>{
  let taskId;
  const {db,api,requests}=await setup(t,async(body,count,db)=>{
    if(count===1)return tool('get_context',{},'read-before');
    if(count===2){
      assert.equal(lastTool(body).focused_task.summary,'Original details');
      await db.write(state=>new Model(state).update(taskId,{summary:'Edited in another tab'}));
      return tool('get_context',{},'read-after');
    }
    assert.equal(lastTool(body).focused_task.summary,'Edited in another tab');
    assert.equal(lastTool(body).already_completed,undefined);
    return response({content:'Current details checked.'});
  });
  taskId=(await db.write(state=>new Model(state).create('Forms','Original details'))).id;
  await api('/chat/jobs',{request_id:'live-context-check',text:'Inspect the current details',task_context:[taskId]});
  await waitFor(()=>db.state.jobs[0]?.status==='done');
  assert.equal(requests.length,3);
});

for(const scenario of ['failed mutation','unchanged read'])test('repeated '+scenario+' stops without an endless provider loop',async t=>{
  const {db,api,requests}=await setup(t,async(body,count)=>{
    // Bound the mock too: a broken loop completes, making the assertions fail
    // promptly instead of leaving the test running indefinitely.
    if(count>5)return response({content:'Synthetic loop safeguard.'});
    return scenario==='failed mutation'
      ? tool('defer_task',{id:'missing-task',when:'tomorrow'},'attempt-'+count)
      : tool('get_context',{},'attempt-'+count);
  });
  await api('/chat/jobs',{request_id:'loop-check-'+scenario.replaceAll(' ','-'),text:'Inspect the selected work'});
  await waitFor(()=>!['queued','running'].includes(db.state.jobs[0]?.status));
  assert.equal(db.state.jobs[0].status,'error');
  assert.match(db.state.jobs[0].error,/repeating the same tool calls/);
  assert.ok(requests.length<=4,'repeated no-progress calls must stop promptly');
  assert.equal(db.state.jobs[0].changes_saved,false);
  assert.equal(db.state.tasks.length,0);
});

test('history tool cannot feed later queued instructions into an earlier request',async t=>{
  let release;const gate=new Promise(resolve=>release=resolve);
  t.after(()=>release());
  const {db,api,requests}=await setup(t,async(body,count)=>{
    if(count===1){await gate;return tool('search_history',{query:'contract',limit:1},'history-read')}
    if(count===2){
      const history=lastTool(body);
      assert.deepEqual(history.messages.map(row=>row.id),['older-contract-note']);
      assert.equal(history.has_more,false);
      assert.ok(!JSON.stringify(history).includes('future instruction'));
    }
    return response({content:'History checked.'});
  });
  await db.write(state=>{state.messages.push({id:'older-contract-note',role:'user',body:'Contract context from an earlier conversation',created_at:'2026-11-01T12:00:00.000Z'});return null});
  await api('/chat/jobs',{request_id:'history-first-request',text:'Search our contract history'});
  await waitFor(()=>requests.length===1);
  await api('/chat/jobs',{request_id:'history-later-request',text:'Contract future instruction from a later queued request'});
  release();
  await waitFor(()=>db.state.jobs.every(job=>job.status==='done'));
  assert.equal(requests.length,3);
});
