/* Encrypted household AI configuration has a separate append-only tab.
   It is never a task record, prompt, portable backup, or plaintext key store.
   read() never creates a tab; append() requires explicit publication consent. */
import {SyncError} from './drive-sync-core.mjs';
const API='https://sheets.googleapis.com/v4/spreadsheets';
const TAB='Household AI',MAX_VERSIONS=200,MAX_BYTES=2*1024*1024,MAX_CIPHERTEXT=32768;
export const HOUSEHOLD_AI_HEADER=['tether-household-ai','1','revision','parents','ciphertext'];
const ID=/^[A-Za-z0-9_-]{8,200}$/;
const JWE=/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
const bytes=value=>new TextEncoder().encode(JSON.stringify(value)).length;
const active=c=>{if(c?.isActive&&!c.isActive())throw new SyncError('Household setup stopped',499)};
function sessionId(s){if(s?.mode!=='selected-sheet'||typeof s.spreadsheetId!=='string'||!ID.test(s.spreadsheetId)||s.workspaceId!==s.spreadsheetId||!Number.isSafeInteger(s.sheetId)||s.sheetId<0)throw new SyncError('Connect a selected household first');return s.spreadsheetId}
function version(v){
  if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!['id','parents','ciphertext'].includes(k))||typeof v.id!=='string'||!ID.test(v.id)||!Array.isArray(v.parents)||v.parents.length>20||v.parents.some(p=>typeof p!=='string'||!ID.test(p)||p===v.id)||new Set(v.parents).size!==v.parents.length||typeof v.ciphertext!=='string'||v.ciphertext.length>MAX_CIPHERTEXT||!JWE.test(v.ciphertext))throw new SyncError('Invalid encrypted household AI version');
  return {id:v.id,parents:[...v.parents].sort(),ciphertext:v.ciphertext};
}
const signature=v=>JSON.stringify(version(v));
function parseRows(rows){
  if(!Array.isArray(rows)||rows.length>MAX_VERSIONS+1||bytes(rows)>MAX_BYTES||JSON.stringify(rows[0])!==JSON.stringify(HOUSEHOLD_AI_HEADER))throw new SyncError('Unsupported household AI settings tab or capacity exceeded');
  const revisions=new Map();let used=0;
  for(const row of rows.slice(1)){
    if(Array.isArray(row)&&(!row.length||row.every(x=>x==='')))continue;
    used++;
    if(!Array.isArray(row)||row.length!==5||row[1]!=='1'||row[4]!=='JWE'||typeof row[2]!=='string'||row[2].length>5000)throw new SyncError('Malformed encrypted household AI row');
    let parents;try{parents=JSON.parse(row[2])}catch(_){throw new SyncError('Invalid household AI revision history')}
    const v=version({id:row[0],parents,ciphertext:row[3]});
    if(revisions.has(v.id)&&signature(revisions.get(v.id))!==signature(v))throw new SyncError('Conflicting duplicate household AI revision');
    revisions.set(v.id,v);
  }
  // Validate the complete graph, not row order: simultaneous valid appends can
  // arrive in either order, and duplicates are harmless.
  const referenced=new Set(),visiting=new Set(),done=new Set();
  const visit=id=>{if(visiting.has(id))throw new SyncError('Cyclic household AI revision history');if(done.has(id))return;const v=revisions.get(id);if(!v)throw new SyncError('Incomplete household AI revision history');visiting.add(id);for(const p of v.parents){referenced.add(p);visit(p)}visiting.delete(id);done.add(id)};
  for(const id of revisions.keys())visit(id);
  const versions=[...revisions.values()].sort((a,b)=>a.id.localeCompare(b.id));
  return {versions,tips:versions.filter(v=>!referenced.has(v.id)),used,bytes:bytes(rows)};
}
export class HouseholdAIStore {
  constructor({transport}){if(typeof transport?.request!=='function')throw new TypeError('A Drive Sheets transport is required');this.transport=transport}
  async metadata(token,id,control){
    const data=await this.transport.request(token,API+'/'+encodeURIComponent(id)+'?fields=spreadsheetId,sheets(properties(sheetId,title,sheetType,gridProperties(rowCount,columnCount)))',{},control);
    if(data.spreadsheetId!==id||!Array.isArray(data.sheets))throw new SyncError('Invalid household spreadsheet metadata');
    const tabs=data.sheets.filter(x=>x.properties?.title===TAB);if(tabs.length>1)throw new SyncError('Duplicate household AI settings tabs');
    if(!tabs.length)return null;
    const p=tabs[0].properties;
    if(!Number.isSafeInteger(p.sheetId)||p.sheetId<0||p.sheetType!=='GRID'||!Number.isSafeInteger(p.gridProperties?.rowCount)||p.gridProperties.rowCount<1||p.gridProperties.rowCount>MAX_VERSIONS+1||p.gridProperties.columnCount!==5)throw new SyncError('Unsupported household AI settings grid or capacity exceeded');
    return p;
  }
  async readState(token,session,control={}){
    active(control);const id=sessionId(session),tab=await this.metadata(token,id,control);active(control);
    if(!tab)return {versions:[],tips:[],used:0,bytes:0,tab:null};
    const range=encodeURIComponent("'Household AI'!A1:E"+(MAX_VERSIONS+1));
    const data=await this.transport.request(token,API+'/'+encodeURIComponent(id)+'/values/'+range+'?valueRenderOption=FORMULA&majorDimension=ROWS',{},control);active(control);
    if(data.majorDimension!==undefined&&data.majorDimension!=='ROWS')throw new SyncError('Malformed household AI settings layout');
    return {...parseRows(data.values||[]),tab};
  }
  async read(token,session,control={}){const s=await this.readState(token,session,control);return {versions:s.versions,tips:s.tips}}
  async ensureTab(token,session,control){
    const id=sessionId(session),existing=await this.readState(token,session,control);if(existing.tab)return existing;
    active(control);
    const sheetId=crypto.getRandomValues(new Uint32Array(1))[0]%2000000000+1;
    const body={requests:[{addSheet:{properties:{sheetId,title:TAB,gridProperties:{rowCount:MAX_VERSIONS+1,columnCount:5,frozenRowCount:1}}}},{updateCells:{start:{sheetId,rowIndex:0,columnIndex:0},rows:[{values:HOUSEHOLD_AI_HEADER.map(stringValue=>({userEnteredValue:{stringValue}}))}],fields:'userEnteredValue'}}]};
    try{await this.transport.request(token,API+'/'+encodeURIComponent(id)+':batchUpdate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)},control)}
    catch(error){
      // A concurrent creator may have won the unique tab title. Only known
      // conflict statuses permit a read-and-validate recovery, never a blind retry.
      if(![400,409].includes(error.status))throw error;
      const raced=await this.readState(token,session,control);if(!raced.tab)throw error;return raced;
    }
    return this.readState(token,session,control);
  }
  async append(token,session,input,control={}){
    if(control.confirmed!==true)throw new SyncError('Confirm publishing the encrypted API key to this household first');
    const id=sessionId(session),v=version(input);active(control);
    const state=await this.ensureTab(token,session,control),existing=state.versions.find(x=>x.id===v.id);
    if(existing){if(signature(existing)!==signature(v))throw new SyncError('Conflicting household AI revision ID');return {versions:state.versions,tips:state.tips}}
    const known=new Set(state.versions.map(x=>x.id));if(v.parents.some(x=>!known.has(x)))throw new SyncError('Household AI settings changed. Reload before publishing.');
    const row=[v.id,'1',JSON.stringify(v.parents),v.ciphertext,'JWE'];
    if(state.used>=MAX_VERSIONS||state.bytes+bytes(row)>MAX_BYTES)throw new SyncError('Household AI settings history is full. No key was uploaded.');
    active(control);
    const result=await this.transport.request(token,API+'/'+encodeURIComponent(id)+'/values/'+encodeURIComponent("'Household AI'!A:E")+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS&includeValuesInResponse=false',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({majorDimension:'ROWS',values:[row]})},control);
    if(result.spreadsheetId!==id||result.updates?.updatedRows!==1)throw new SyncError('Google did not confirm the encrypted settings upload. Retry checks for the existing revision first.');
    // A concurrent publisher may have created another tip. Return all choices;
    // a caller must never silently pick the last spreadsheet row.
    return this.read(token,session,control);
  }
}
