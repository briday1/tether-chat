import test from 'node:test';
import assert from 'node:assert/strict';
import {HouseholdAIStore,HOUSEHOLD_AI_HEADER} from '../../web/household-ai-store.mjs';
import {DriveSheets} from '../../web/drive-sheets.mjs';
const id='spreadsheet_123',session={mode:'selected-sheet',spreadsheetId:id,workspaceId:id,sheetId:0};
const cipher='eyJhbGciOiJkZW1vIn0.ZGVtbw.ZGVtbw.ZGVtbw.ZGVtbw';
const rev=(name,parents=[])=>({id:name,parents,ciphertext:cipher});
const row=v=>[v.id,'1',JSON.stringify(v.parents),v.ciphertext,'JWE'];
function server({exists=false,rows=[HOUSEHOLD_AI_HEADER]}={}){
  const calls=[],state={exists,rows:structuredClone(rows),lose:false,race:false,gridRows:201};
  const response=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
  const fetcher=async(url,o)=>{
    calls.push({url,o});const u=new URL(url);
    if(u.pathname.endsWith(':batchUpdate')){
      const body=JSON.parse(o.body);assert.equal(body.requests[0].addSheet.properties.title,'Household AI');assert.deepEqual(body.requests[1].updateCells.rows[0].values.map(x=>x.userEnteredValue.stringValue),HOUSEHOLD_AI_HEADER);state.exists=true;
      if(state.race)return response({},400);return response({spreadsheetId:id});
    }
    if(u.pathname.endsWith(':append')){
      assert.equal(u.searchParams.get('valueInputOption'),'RAW');assert.equal(u.searchParams.get('insertDataOption'),'INSERT_ROWS');const body=JSON.parse(o.body);state.rows.push(...body.values);
      if(state.lose){state.lose=false;throw Error('Synthetic connection interruption')}
      return response({spreadsheetId:id,updates:{updatedRows:1}});
    }
    if(u.pathname.includes('/values/')){assert.ok(decodeURIComponent(u.pathname).includes("'Household AI'"));return response({majorDimension:'ROWS',values:state.rows});}
    return response({spreadsheetId:id,sheets:[{properties:{sheetId:0,title:'Journal',sheetType:'GRID',gridProperties:{rowCount:1000,columnCount:5}}},...(state.exists?[{properties:{sheetId:9,title:'Household AI',sheetType:'GRID',gridProperties:{rowCount:state.gridRows,columnCount:5}}}]:[])]});
  };
  return {calls,state,store:new HouseholdAIStore({transport:new DriveSheets(fetcher)})};
}
const consent={confirmed:true};
test('read absent AI settings is non-mutating and never reads task Journal rows',async()=>{const s=server();assert.deepEqual(await s.store.read('synthetic-token',session),{versions:[],tips:[]});assert.equal(s.calls.length,1);assert.ok(s.calls.every(x=>!x.o.method))});
test('publish requires explicit consent before any request',async()=>{const s=server();await assert.rejects(s.store.append('synthetic-token',session,rev('revision_1')),/Confirm publishing/);assert.equal(s.calls.length,0)});
test('first append atomically creates isolated tab/header and appends encrypted revision',async()=>{const s=server(),v=rev('revision_1');assert.deepEqual(await s.store.append('synthetic-token',session,v,consent),{versions:[v],tips:[v]});assert.equal(s.calls.filter(c=>c.url.endsWith(':batchUpdate')).length,1);assert.ok(s.calls.every(c=>!['PUT','PATCH'].includes(c.o.method)));assert.ok(s.calls.filter(c=>c.o.body).every(c=>!c.o.body.includes('synthetic-token')));assert.ok(s.calls.every(c=>c.o.credentials==='omit'&&c.o.redirect==='error'));});
test('concurrent tab creation conflict is read/validated, not rewritten',async()=>{const s=server();s.state.race=true;await s.store.append('synthetic-token',session,rev('revision_1'),consent);assert.equal(s.calls.filter(c=>c.url.endsWith(':batchUpdate')).length,1)});
test('uncertain append retry finds identical revision and does not append again',async()=>{const s=server({exists:true});s.state.lose=true;const v=rev('revision_1');await assert.rejects(s.store.append('synthetic-token',session,v,consent),/interruption/);assert.deepEqual(await s.store.append('synthetic-token',session,v,consent),{versions:[v],tips:[v]});assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,1)});
test('parallel configuration branches remain explicit tips until combined update',async()=>{const a=rev('revision_a'),b=rev('revision_b'),c=rev('revision_c',['revision_a','revision_b']);const s=server({exists:true,rows:[HOUSEHOLD_AI_HEADER,row(a),row(b)]});assert.deepEqual((await s.store.read('s',session)).tips,[a,b]);assert.deepEqual((await s.store.append('s',session,c,consent)).tips,[c]);});
test('duplicate identical rows deduplicate but conflicting duplicate IDs fail closed',async()=>{const a=rev('revision_a'),s=server({exists:true,rows:[HOUSEHOLD_AI_HEADER,row(a),row(a)]});assert.deepEqual((await s.store.read('s',session)).versions,[a]);s.state.rows.push(row({...a,ciphertext:cipher+'x'}));await assert.rejects(s.store.read('s',session),/Conflicting duplicate/)});
test('malformed headers, formulas, private extras, invalid ciphertext, missing ancestors and cycles rejected',async()=>{
  const a=rev('revision_a');
  for(const rows of [[],[['bad']], [HOUSEHOLD_AI_HEADER,['revision_a','1','[]','=IMPORTDATA("evil")','JWE']], [HOUSEHOLD_AI_HEADER,row(rev('revision_a',['missing_id']))], [HOUSEHOLD_AI_HEADER,row(rev('revision_a',['revision_b'])),row(rev('revision_b',['revision_a']))]]){const s=server({exists:true,rows});await assert.rejects(s.store.read('s',session));}
  for(const v of [{...a,api_key:'synthetic'}, {...a,parents:['revision_a']}, {...a,ciphertext:'plaintext'}, {...a,ciphertext:'a'.repeat(40000)}, {...a,id:12345678}, {...a,parents:Array(21).fill('revision_b')}]){const s=server();await assert.rejects(s.store.append('s',session,v,consent));assert.equal(s.calls.length,0)}
});
test('missing parent prevents append and existing ID cannot silently change',async()=>{const a=rev('revision_a'),s=server({exists:true,rows:[HOUSEHOLD_AI_HEADER,row(a)]});await assert.rejects(s.store.append('s',session,rev('revision_b',['missing_id']),consent),/changed/);await assert.rejects(s.store.append('s',session,{...a,ciphertext:cipher+'x'},consent),/Conflicting/);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,0)});
test('capacity, invalid selected session and cancellation prevent writes',async()=>{const s=server({exists:true});s.state.gridRows=202;await assert.rejects(s.store.read('s',session),/capacity/);await assert.rejects(s.store.append('s',{...session,workspaceId:'different_id'},rev('revision_a'),consent));await assert.rejects(s.store.append('s',session,rev('revision_a'),{confirmed:true,isActive:()=>false}),e=>e.status===499);assert.equal(s.calls.filter(c=>c.o.method).length,0)});
test('full 200 revision history cannot append and aggregate bytes bounded',async()=>{const rows=[HOUSEHOLD_AI_HEADER,...Array.from({length:200},(_,i)=>row(rev('revision_'+i)))],s=server({exists:true,rows});await assert.rejects(s.store.append('s',session,rev('new_revision'),consent),/history is full/);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,0);const huge='aaaa.bbbb.cccc.'+'d'.repeat(30000)+'.eeee';s.state.rows=[HOUSEHOLD_AI_HEADER,...Array.from({length:100},(_,i)=>row({...rev('revision_'+i),ciphertext:huge}))];await assert.rejects(s.store.read('s',session),/capacity/)});
