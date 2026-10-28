/* Backend-free Home journal: append-only rows in an explicitly selected Sheet.
   Each operation is appended in one request; uncertain retries are deduplicated
   by immutable operation ID and exact chunk content. No overwrite requests. */
import {mergeJournal,stable,SyncError} from './drive-sync-core.mjs';
const API='https://sheets.googleapis.com/v4/spreadsheets';
const MAX_BYTES=8*1024*1024,MAX_ROWS=50000,CHUNK=30000,MAX_APPEND=1024*1024,PAGE=1000;
export const SHEET_HEADER=['tether-home-journal','1','operation-id','chunk-index/count','json'];
const idPattern=/^[A-Za-z0-9_-]{8,200}$/;
const active=c=>{if(c?.isActive&&!c.isActive())throw new SyncError('Sync stopped',499)};
const validId=id=>typeof id==='string'&&idPattern.test(id);
const integer=value=>Number.isSafeInteger(value)&&value>=0;
const numeric=value=>typeof value==='number'?value:typeof value==='string'&&/^(0|[1-9][0-9]*)$/.test(value)?Number(value):NaN;
function checkSession(s){if(!s||s.mode!=='selected-sheet'||!validId(s.spreadsheetId)||s.workspaceId!==s.spreadsheetId||!integer(s.sheetId))throw new SyncError('Select a valid shared Home spreadsheet first');return s}
function rowsFor(op){const text=stable(op),chunks=[];for(let i=0;i<text.length;i+=CHUNK)chunks.push(text.slice(i,i+CHUNK));const rows=chunks.map((chunk,index)=>[op.id,'1',String(index),String(chunks.length),chunk]);if(new TextEncoder().encode(JSON.stringify({majorDimension:'ROWS',values:rows})).length>MAX_APPEND)throw new SyncError('A Home edit exceeds the 1 MB upload limit. Local changes were kept.');return rows}
export class DriveSheets {
  constructor(fetcher=globalThis.fetch.bind(globalThis)){this.fetcher=typeof fetcher==='function'?fetcher:fetcher.fetcher;this.lastParticipants=[];this.pollDelayMs=30000;this.notBefore=0;this.retryAfterMs=0;this.rateFailures=0}
  async request(token,url,options={},control={}){
    active(control);const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),25000);
    try{
      const response=await this.fetcher(url,{...options,signal:abort.signal,credentials:'omit',redirect:'error',cache:'no-store',headers:{Authorization:'Bearer '+token,...options.headers}});active(control);
      if(response.status===429){const retry=response.headers?.get('retry-after'),seconds=Number(retry),date=Date.parse(retry||'');this.rateFailures++;this.retryAfterMs=Math.min(3600000,Math.max(30000,retry&&Number.isFinite(seconds)?seconds*1000:Number.isFinite(date)?date-Date.now():30000*2**Math.min(this.rateFailures-1,6)));this.notBefore=Date.now()+this.retryAfterMs}
      if(!response.ok)throw new SyncError(response.status===401?'Google authorization expired':response.status===403?'Google Sheets denied access. Enable the Sheets API and select this spreadsheet with Google Picker using the correct account.':`Google Sheets request failed (${response.status})`,response.status);
      if(Number(response.headers?.get('content-length'))>MAX_BYTES)throw new SyncError('The shared Home journal exceeds the 8 MB limit');
      let text;
      if(response.body?.getReader){const reader=response.body.getReader(),parts=[];let size=0;try{while(true){const r=await reader.read();if(r.done)break;size+=r.value.byteLength;if(size>MAX_BYTES){await reader.cancel();throw new SyncError('The shared Home journal exceeds the 8 MB limit')}parts.push(r.value)}}finally{reader.releaseLock()}const bytes=new Uint8Array(size);let offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.byteLength}try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch(_){throw new SyncError('Invalid UTF-8 in shared Home journal')}}else{text=await response.text();if(new TextEncoder().encode(text).length>MAX_BYTES)throw new SyncError('The shared Home journal exceeds the 8 MB limit')}
      active(control);try{return text?JSON.parse(text):{}}catch(_){throw new SyncError('Google Sheets returned an invalid response')}
    }finally{clearTimeout(timer)}
  }
  async metadata(token,id,control={}){
    if(!validId(id))throw new SyncError('Invalid shared spreadsheet ID');
    const data=await this.request(token,API+'/'+encodeURIComponent(id)+'?fields=spreadsheetId,properties(title),sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)))',{},control);
    const tabs=Array.isArray(data.sheets)?data.sheets.filter(s=>s.properties?.title==='Journal'):[];
    if(data.spreadsheetId!==id||tabs.length!==1)throw new SyncError('This spreadsheet has no unique Tether Journal tab');
    const p=tabs[0].properties;
    if(!integer(p.sheetId)||p.sheetType!=='GRID'||!integer(p.gridProperties?.rowCount)||p.gridProperties.rowCount<1||p.gridProperties.rowCount>MAX_ROWS||p.gridProperties.columnCount<5)throw new SyncError('Unsupported journal grid or 50,000-row limit exceeded');
    return {id,name:typeof data.properties?.title==='string'?data.properties.title:'Shared Home',sheetId:p.sheetId,rowCount:p.gridProperties.rowCount};
  }
  async values(token,id,from,to,control={}){
    const data=await this.request(token,API+'/'+encodeURIComponent(id)+'/values/'+encodeURIComponent("'Journal'!A"+from+':E'+to)+'?valueRenderOption=FORMULA&majorDimension=ROWS',{},control);
    if(data.majorDimension!==undefined&&data.majorDimension!=='ROWS')throw new SyncError('Malformed journal row layout');
    const rows=data.values??[];if(!Array.isArray(rows)||rows.length>to-from+1)throw new SyncError('Malformed journal rows');return rows;
  }
  async inspectHousehold(token,id,control={}){
    const meta=await this.metadata(token,id,control),header=await this.values(token,id,1,1,control);
    if(stable(header)!==stable([SHEET_HEADER]))throw new SyncError('This spreadsheet is not a supported Tether Home journal');
    const {rowCount,...result}=meta;return result;
  }
  async createHousehold(token,name,control={}){
    if(typeof name!=='string'||!name.trim()||name.length>160||/[\x00-\x1f]/.test(name))throw new SyncError('Use a short household name');
    const title='Tether · '+name.trim();
    // Header and tab are created atomically with the spreadsheet, not a second
    // initialization write that could strand an apparently valid empty file.
    const result=await this.request(token,API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({properties:{title},sheets:[{properties:{sheetId:0,title:'Journal',gridProperties:{rowCount:1000,columnCount:5,frozenRowCount:1}},data:[{startRow:0,startColumn:0,rowData:[{values:SHEET_HEADER.map(stringValue=>({userEnteredValue:{stringValue}}))}]}]}]})},control);
    if(!validId(result.spreadsheetId))throw new SyncError('Google did not confirm the new spreadsheet ID');
    return {id:result.spreadsheetId,name:title,sheetId:0};
  }
  async pull(token,session,control={}){
    const s=checkSession(session),meta=await this.metadata(token,s.spreadsheetId,control);
    if(meta.sheetId!==s.sheetId)throw new SyncError('The selected Journal tab changed. Re-select the household.');
    const pieces=new Map();let bytes=0,total=0,usedRows=1;
    for(let from=1;from<=meta.rowCount;from+=PAGE){
      const rows=await this.values(token,s.spreadsheetId,from,Math.min(meta.rowCount,from+PAGE-1),control);
      bytes+=new TextEncoder().encode(JSON.stringify(rows)).length;if(bytes>MAX_BYTES)throw new SyncError('The shared Home journal exceeds the 8 MB limit');
      for(let offset=0;offset<rows.length;offset++){
        const row=rows[offset];if(from===1&&offset===0){if(stable(row)!==stable(SHEET_HEADER))throw new SyncError('Unsupported shared Home journal header');continue}
        if(!Array.isArray(row))throw new SyncError('Malformed journal row');
        if(row.length===0||row.every(v=>v===''))continue;
        usedRows=Math.max(usedRows,from+offset);
        if(++total>MAX_ROWS||row.length!==5||typeof row[0]!=='string'||!idPattern.test(row[0])||String(row[1])!=='1'||typeof row[4]!=='string'||row[4].length>CHUNK)throw new SyncError('Malformed shared Home operation chunk');
        const index=numeric(row[2]),count=numeric(row[3]);if(!integer(index)||!integer(count)||count<1||count>100||index>=count)throw new SyncError('Invalid shared Home chunk index');
        let entry=pieces.get(row[0]);if(!entry){entry={count,parts:new Map()};pieces.set(row[0],entry)}
        if(entry.count!==count||(entry.parts.has(index)&&entry.parts.get(index)!==row[4]))throw new SyncError('Conflicting duplicate shared Home operation chunks');
        entry.parts.set(index,row[4]);
      }
      if(from===1&&!rows.length)throw new SyncError('Missing shared Home journal header');
    }
    const log=[];
    for(const [id,entry] of pieces){if(entry.parts.size!==entry.count)throw new SyncError('Incomplete shared Home operation. Retry after the other device finishes syncing.');const text=Array.from({length:entry.count},(_,i)=>entry.parts.get(i)).join('');if(new TextEncoder().encode(text).length>MAX_APPEND)throw new SyncError('A shared Home operation exceeds the 1 MB limit');let op;try{op=JSON.parse(text)}catch(_){throw new SyncError('Invalid JSON in shared Home operation')}if(op?.id!==id)throw new SyncError('Shared Home operation ID does not match its row');log.push(op)}
    const merged=mergeJournal(log);this.pollDelayMs=Math.max(30000,(2*(Math.ceil(meta.rowCount/PAGE)+1)+2)*2000);this.notBefore=Math.max(this.notBefore,Date.now()+this.pollDelayMs);this.rateFailures=0;this.retryAfterMs=0;this.usedRows=usedRows;this.usedBytes=bytes;return merged;
  }
  async push(token,session,log,_actor,_uploaded,control={}){
    const s=checkSession(session),remote=await this.pull(token,s,control),merged=mergeJournal(remote,log),present=new Set(remote.map(op=>op.id)),done=[];
    // Validate and size every pending operation before sending any of this batch.
    const pending=merged.filter(op=>!present.has(op.id)).map(op=>({op,rows:rowsFor(op)}));
    if(this.usedRows+pending.reduce((sum,item)=>sum+item.rows.length,0)>MAX_ROWS)throw new SyncError('The shared Home journal reached its 50,000-row limit. Local changes were kept.');
    if(this.usedBytes+pending.reduce((sum,item)=>sum+new TextEncoder().encode(JSON.stringify(item.rows)).length,0)>MAX_BYTES)throw new SyncError('The shared Home journal reached its 8 MB limit. Local changes were kept.');
    // At most ten append requests per cycle; the remainder stays in the local
    // durable journal and is picked up on a later poll, not marked uploaded.
    for(const {op,rows} of pending.slice(0,10)){
      active(control);
      const result=await this.request(token,API+'/'+encodeURIComponent(s.spreadsheetId)+'/values/'+encodeURIComponent("'Journal'!A:E")+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS&includeValuesInResponse=false',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({majorDimension:'ROWS',values:rows})},control);
      if(result.spreadsheetId!==s.spreadsheetId||result.updates?.updatedRows!==rows.length)throw new SyncError('Google did not confirm the complete Home append. Retry will check for an existing copy.');done.push(op.id);
    }
    return [...present,...done];
  }
}
