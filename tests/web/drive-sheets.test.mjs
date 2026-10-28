import test from 'node:test';import assert from 'node:assert/strict';
import {DriveSheets,SHEET_HEADER} from '../../web/drive-sheets.mjs';
import {makeChanges,stable} from '../../web/drive-sync-core.mjs';
const id='spreadsheet_12345',when='2026-10-28T00:00:00Z',actor='device_12345';
const task={id:'task1',title:'Milk',summary:'',state:'open',categories:['Home'],revisit_at:null,due_at:null,recurrence:null,next_occurrence:null,archived_at:null,created_at:when,updated_at:when};
const records={'task:task1':task},op=makeChanges([],{},records,actor,'operation_0001',when);
const session={mode:'selected-sheet',spreadsheetId:id,workspaceId:id,sheetId:0};
const response=(data,status=200,headers={})=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json',...headers}});
const encode=op=>{const text=stable(op),chunks=[];for(let i=0;i<text.length;i+=30000)chunks.push(text.slice(i,i+30000));return chunks.map((part,i)=>[op.id,'1',String(i),String(chunks.length),part])};
function server({rows=[SHEET_HEADER],rowCount=1000,sheetId=0}={}){
  const calls=[];const state={rows:structuredClone(rows),rowCount,loseAppend:false};
  const fetcher=async(url,options)=>{
    calls.push({url,options});const u=new URL(url);
    if(options.method==='POST'&&!u.pathname.includes(':append')){const body=JSON.parse(options.body);assert.deepEqual(body.sheets[0].data[0].rowData[0].values.map(c=>c.userEnteredValue.stringValue),SHEET_HEADER);return response({spreadsheetId:id})}
    if(u.pathname.endsWith(':append')){assert.equal(u.searchParams.get('valueInputOption'),'RAW');assert.equal(u.searchParams.get('insertDataOption'),'INSERT_ROWS');const values=JSON.parse(options.body).values;state.rows.push(...values);if(state.loseAppend){state.loseAppend=false;throw new Error('Lost response after append')}return response({spreadsheetId:id,updates:{updatedRows:values.length}})}
    if(u.pathname.includes('/values/')){const range=decodeURIComponent(u.pathname.split('/values/')[1]);const match=/A(\d+):E(\d+)/.exec(range);assert.ok(match);return response({majorDimension:'ROWS',values:state.rows.slice(Number(match[1])-1,Number(match[2]))})}
    return response({spreadsheetId:id,properties:{title:'Tether · Home'},sheets:[{properties:{sheetId,title:'Journal',sheetType:'GRID',gridProperties:{rowCount:state.rowCount,columnCount:5}}}]});
  };
  return {state,calls,fetcher,transport:new DriveSheets(fetcher)};
}
test('create atomically creates header and Journal in one request',async()=>{const s=server();assert.deepEqual(await s.transport.createHousehold('secret','Home'),{id,name:'Tether · Home',sheetId:0});assert.equal(s.calls.length,1);assert.equal(s.calls[0].options.headers.Authorization,'Bearer secret');assert.equal(s.calls[0].options.credentials,'omit');assert.ok(!s.calls[0].options.body.includes('secret'))});
test('inspect validates selected spreadsheet header and numeric tab identity',async()=>{const s=server();assert.deepEqual(await s.transport.inspectHousehold('s',id),{id,name:'Tether · Home',sheetId:0});s.state.rows[0]=['bad'];await assert.rejects(s.transport.inspectHousehold('s',id),/not a supported/)});
test('pull reconstructs chunks and deduplicates identical immutable rows',async()=>{const big={...task,summary:'x'.repeat(20000)};const operation=makeChanges([],{}, {'task:task1':big,'task:task2':{...big,id:'task2'}},actor,'operation_big1',when);const rows=encode(operation),s=server({rows:[SHEET_HEADER,...rows,...rows]});assert.deepEqual(await s.transport.pull('s',session),[operation]);assert.ok(rows.length>1)});
test('pull scans beyond blank pages instead of silently truncating history',async()=>{const rows=[SHEET_HEADER];rows[2001]=encode(op)[0];for(let i=1;i<2001;i++)rows[i]=[];const s=server({rows,rowCount:3000});assert.deepEqual(await s.transport.pull('s',session),[op]);assert.equal(s.calls.filter(c=>c.url.includes('/values/')).length,3);assert.ok(s.transport.notBefore>Date.now())});
test('append uses RAW INSERT_ROWS and one atomic request per complete operation',async()=>{const s=server();assert.deepEqual(await s.transport.push('s',session,[op],actor,[]),[op.id]);const append=s.calls.filter(c=>c.url.includes(':append'));assert.equal(append.length,1);assert.deepEqual(JSON.parse(append[0].options.body).values,encode(op));assert.deepEqual(await s.transport.pull('s',session),[op]);assert.ok(s.calls.every(c=>c.options.method!=='PATCH'&&c.options.method!=='PUT'))});
test('uncertain append retries deduplicate before sending again',async()=>{const s=server();s.state.loseAppend=true;await assert.rejects(s.transport.push('s',session,[op],actor,[]),/Lost response/);assert.deepEqual(await s.transport.push('s',session,[op],actor,[]),[op.id]);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,1)});
test('two devices can append same operation concurrently without overwrite',async()=>{const s=server(),a=new DriveSheets(s.fetcher),b=new DriveSheets(s.fetcher);await Promise.all([a.push('a',session,[op],actor,[]),b.push('b',session,[op],actor,[])]);assert.deepEqual(await a.pull('a',session),[op]);assert.equal(s.state.rows.length,3)});
test('conflicting duplicate, missing chunks, malformed rows and private fields fail closed',async()=>{
  const row=encode(op)[0];for(const rows of [[row,[...row.slice(0,4),'different']],[{bad:true}],[[op.id,'1','0','2',row[4]]],[[op.id,'1','0','1','=IMPORTDATA("x")']],[[op.id,'2','0','1',row[4]]],[[op.id,'1','-1','1',row[4]]],[[op.id,'1','0','1',JSON.stringify({...op,secret:'private'})]],[[op.id,'1','0','1',JSON.stringify({...op,id:'operation_other'})]]]){const s=server({rows:[SHEET_HEADER,...rows]});await assert.rejects(s.transport.pull('s',session));assert.ok(s.calls.every(c=>!c.options.method))}
});
test('strict selected session, replaced tab, grid limits and missing header rejected',async()=>{for(const altered of [{...session,mode:'folder-records'},{...session,workspaceId:'another_workspace'},{...session,sheetId:'0'}]){const s=server();await assert.rejects(s.transport.pull('s',altered));assert.equal(s.calls.length,0)}for(const opts of [{sheetId:1},{rowCount:50001},{rows:[]}]){const s=server(opts);await assert.rejects(s.transport.pull('s',session))}});
test('oversized operation fails before any append and preserves local log',async()=>{const huge={};for(let i=0;i<60;i++)huge['task:t'+i]={...task,id:'t'+i,summary:'x'.repeat(20000)};const operation=makeChanges([],{},huge,actor,'operation_huge',when),s=server();await assert.rejects(s.transport.push('s',session,[operation],actor,[]),/1 MB/);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,0)});
test('stop and expired authorization halt without follow-on writes',async()=>{const s=server();await assert.rejects(s.transport.push('s',session,[op],actor,[],{isActive:()=>false}),e=>e.status===499);assert.equal(s.calls.length,0);const t=new DriveSheets(async()=>response({},401));await assert.rejects(t.pull('s',session),e=>e.status===401)});
test('rate limits expose retry deadline and large grids reduce polling frequency',async()=>{const t=new DriveSheets(async()=>response({},429,{'Retry-After':'120'}));const now=Date.now();await assert.rejects(t.pull('s',session),e=>e.status===429);assert.equal(t.retryAfterMs,120000);assert.ok(t.notBefore>=now+120000);const s=server({rowCount:50000});await s.transport.pull('s',session);assert.ok(s.transport.pollDelayMs>=208000)});
test('append acknowledgment must confirm all rows; retry reads existing operation',async()=>{const s=server(),base=s.transport.fetcher;s.transport.fetcher=async(url,options)=>{const result=await base(url,options);return url.includes(':append')?response({spreadsheetId:id,updates:{updatedRows:0}}):result};await assert.rejects(s.transport.push('s',session,[op],actor,[]),/did not confirm/);assert.deepEqual(await s.transport.push('s',session,[op],actor,[]),[op.id])});
test('row capacity checked before append so pending history remains readable',async()=>{
  const rows=Array.from({length:50000},()=>[]);rows[0]=SHEET_HEADER;rows[49999]=encode(op)[0];const s=server({rows,rowCount:50000});const changed=structuredClone(records);changed['task:task1'].title='Bread';const next=makeChanges([op],records,changed,actor,'operation_0002',when);await assert.rejects(s.transport.push('s',session,[op,next],actor,[]),/50,000-row/);assert.equal(s.transport.usedRows,50000);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,0);
});
test('each cycle caps append quota and leaves remaining operations pending for retry',async()=>{
  const log=[];for(let i=0;i<12;i++)log.push(makeChanges([],{}, {['task:t'+i]:{...task,id:'t'+i}},actor,'operation_quota'+i,when));const s=server();const first=await s.transport.push('s',session,log,actor,[]);assert.equal(first.length,10);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,10);const second=await s.transport.push('s',session,log,actor,first);assert.equal(second.length,12);assert.equal(s.calls.filter(c=>c.url.includes(':append')).length,12);
});
test('successful full pull clears rate-limit flag but retains normal polling deadline',async()=>{const s=server();s.transport.retryAfterMs=60000;await s.transport.pull('s',session);assert.equal(s.transport.retryAfterMs,0);assert.ok(s.transport.notBefore>Date.now())});
test('aggregate byte capacity checked before append and oversized responses rejected',async()=>{
  const s=server();s.transport.pull=async()=>{s.transport.usedRows=1;s.transport.usedBytes=8*1024*1024-1;return []};await assert.rejects(s.transport.push('s',session,[op],actor,[]),/8 MB/);assert.equal(s.calls.length,0);
  const t=new DriveSheets(async()=>response({},200,{'Content-Length':String(9*1024*1024)}));await assert.rejects(t.pull('s',session),/8 MB/);
});
test('chunk boundaries preserve emoji surrogate pairs across Sheets cells',async()=>{
  const rows={'task:task1':{...task,summary:'x'.repeat(20000)},'task:task2':{...task,id:'task2',summary:'😀'}};
  let operation=makeChanges([],{},rows,actor,'operation_unicode',when);const offset=stable(operation).indexOf('😀');
  rows['task:task2'].summary='y'.repeat(29999-offset)+'😀';operation=makeChanges([],{},rows,actor,'operation_unicode',when);assert.equal(stable(operation).indexOf('😀'),29999);
  const s=server();await s.transport.push('s',session,[operation],actor,[]);
  const chunks=s.state.rows.slice(1).map(row=>row[4]);assert.ok(chunks.length>1);
  for(const chunk of chunks){assert.ok(chunk.length<=30000);assert.equal(chunk.isWellFormed(),true)}
  assert.equal(chunks.join(''),stable(operation));assert.deepEqual(await s.transport.pull('s',session),[operation]);
});
