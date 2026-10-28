/* Narrow drive.file transport: explicitly selected, single-writer journal files.
   Folder permissions do not imply OAuth access to peer files. No folder discovery. */
import {DriveFiles,uuid} from './drive-sync-service.mjs';
import {mergeJournal,stable,SyncError} from './drive-sync-core.mjs';
const API='https://www.googleapis.com/drive/v3/files/';
const UPLOAD='https://www.googleapis.com/upload/drive/v3/files/';
const MAX_BYTES=8*1024*1024;
const identifier=/^[A-Za-z0-9_-]{8,200}$/;
const validId=value=>typeof value==='string'&&identifier.test(value);
const plain=value=>!!value&&typeof value==='object'&&!Array.isArray(value)&&(Object.getPrototypeOf(value)===null||Object.getPrototypeOf(Object.getPrototypeOf(value))===null);
const active=control=>{if(control?.isActive&&!control.isActive())throw new SyncError('Sync stopped',499)};
function sessionFiles(session){
  if(!plain(session)||session.mode!=='selected-journals'||!validId(session.workspaceId)||!Array.isArray(session.files)||session.files.length>50)throw new SyncError('Select the shared Home journal files first');
  const seen=new Set();
  for(const file of session.files){if(!plain(file)||!validId(file.id)||seen.has(file.id))throw new SyncError('Invalid or duplicate selected Drive journal');seen.add(file.id)}
  return session.files;
}
function envelope(data,workspace){
  if(!plain(data)||Object.keys(data).sort().join(',')!=='format,operations,version,workspace,writer'||data.format!=='tether-home-journal'||data.version!==1||data.workspace!==workspace||!validId(data.writer)||!Array.isArray(data.operations)||data.operations.length>50000)throw new SyncError('This file is not a journal for the selected shared Home');
  const operations=mergeJournal(data.operations);
  return {...data,operations};
}
async function boundedText(response){
  if(Number(response.headers?.get('content-length'))>MAX_BYTES)throw new SyncError('Drive journal exceeds the 8 MB limit');
  if(response.body?.getReader){
    const reader=response.body.getReader(),parts=[];let size=0;
    try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>MAX_BYTES){await reader.cancel();throw new SyncError('Drive journal exceeds the 8 MB limit')}parts.push(value)}}finally{reader.releaseLock()}
    const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.byteLength}
    try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch(_){throw new SyncError('Drive journal is not valid UTF-8')}
  }
  const text=await response.text();if(new TextEncoder().encode(text).length>MAX_BYTES)throw new SyncError('Drive journal exceeds the 8 MB limit');return text;
}
export class DriveJournals extends DriveFiles {
  constructor(options={}){const {fileId='',deviceId='',conditionalVerified=false,fetcher=globalThis.fetch.bind(globalThis)}=typeof options==='function'?{fetcher:options}:options;super(fetcher);this.binding=fileId&&deviceId?{fileId,deviceId,conditionalVerified}:null;this.createdHere=new Map();this.lastParticipants=[]}
  async raw(token,url,options={},control={}){
    active(control);const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
    try{
      const response=await this.fetcher(url,{...options,signal:controller.signal,credentials:'omit',redirect:'error',cache:'no-store',headers:{Authorization:'Bearer '+token,...options.headers}});
      active(control);
      if(!response.ok)throw new SyncError(response.status===401?'Google authorization expired':response.status===403?'Google Drive denied access. Select this journal with Google Picker using the correct account.':response.status===412?'The journal changed during upload. Retry to merge the latest copy.':`Google Drive request failed (${response.status})`,response.status);
      const text=await boundedText(response);active(control);
      let data={};try{data=text?JSON.parse(text):{}}catch(_){throw new SyncError('Drive returned an invalid journal response')}
      return {data,etag:response.headers?.get('etag')||''};
    }finally{clearTimeout(timer)}
  }
  async getJournal(token,fileId,workspaceId,control={}){
    if(!validId(fileId)||!validId(workspaceId))throw new SyncError('Invalid shared journal ID');
    const result=await this.raw(token,API+encodeURIComponent(fileId)+'?alt=media',{},control);
    return {journal:envelope(result.data,workspaceId),etag:result.etag};
  }
  async readJournal(token,fileId,workspaceId,control={}){return this.getJournal(token,fileId,workspaceId,control)}
  async createJournal(token,folderId,workspaceId,deviceId,control={}){
    active(control);
    if(!validId(folderId)||!validId(workspaceId)||!validId(deviceId))throw new SyncError('Choose a folder and valid shared Home/device identifiers');
    if(control.name!==undefined&&(typeof control.name!=='string'||!control.name.trim()||control.name.length>200||/[\x00-\x1f]/.test(control.name)))throw new SyncError('Use a short readable journal filename.');
    const name=control.name?.trim()||'tether-home-'+deviceId+'.json';
    const created=await this.create(token,folderId,name,{format:'tether-home-journal',version:1,workspace:workspaceId,writer:deviceId,operations:[]});
    if(!validId(created.id))throw new SyncError('Google did not confirm the new journal ID');
    // An already-sent creation may finish after Stop. Do not retry it automatically.
    this.createdHere.set(created.id,{workspaceId,deviceId});
    return created;
  }
  async probeEmptyConditionalWrite(token,fileId,journal,etag,control={}){
    active(control);
    if(journal.operations.length!==0)throw new SyncError('A safety probe cannot modify a journal containing task data.');
    if(!/^"[^"\r\n]+"$/.test(etag))throw new SyncError('Google did not expose a strong ETag. Shared editing is unavailable in this browser.');
    let impossible;do{impossible='"tether-precondition-probe-'+uuid()+'"'}while(impossible===etag);
    try{
      // Even a server ignoring this precondition receives only the original empty envelope.
      await this.raw(token,UPLOAD+encodeURIComponent(fileId)+'?uploadType=media&fields=id',{method:'PATCH',headers:{'Content-Type':'application/json; charset=UTF-8','If-Match':impossible},body:JSON.stringify(journal)},control);
    }catch(error){if(error.status===412)return;throw error}
    throw new SyncError('Google did not enforce conditional journal writes. Shared editing is disabled to protect your data.');
  }
  async verifyConditionalWrites(token,fileId,workspaceId,deviceId,control={}){
    active(control);
    const created=this.createdHere.get(fileId);
    if(!created||created.workspaceId!==workspaceId||created.deviceId!==deviceId)throw new SyncError('Conditional-write verification is allowed only for a journal just created on this device.');
    const {journal,etag}=await this.getJournal(token,fileId,workspaceId,control);
    if(journal.writer!==deviceId||journal.operations.length!==0)throw new SyncError('Conditional-write verification requires this device’s new empty journal. No data was changed.');
    await this.probeEmptyConditionalWrite(token,fileId,journal,etag,control);
    this.createdHere.delete(fileId);return {conditionalVerified:true};
  }
  async resumeClaim(token,fileId,workspaceId,deviceId,control={}){
    // Caller must hold durable local intent for this exact file/device. This is
    // recovery, never permission to adopt another device's or populated journal.
    if(!validId(deviceId)||deviceId==='unclaimed')throw new SyncError('Invalid device identity for setup recovery.');
    const {journal,etag}=await this.getJournal(token,fileId,workspaceId,control);
    if(journal.writer!==deviceId||journal.operations.length!==0)throw new SyncError('Setup recovery requires this device’s empty journal. No data was changed.');
    await this.probeEmptyConditionalWrite(token,fileId,journal,etag,control);
    return {fileId,deviceId,conditionalVerified:true};
  }
  async createPartnerSlot(token,folderId,workspaceId,control={}){
    return this.createJournal(token,folderId,workspaceId,'unclaimed',control);
  }
  async claimSlot(token,fileId,workspaceId,deviceId,control={}){
    active(control);
    if(!validId(deviceId)||deviceId==='unclaimed')throw new SyncError('This device needs its own writer identity.');
    let {journal,etag}=await this.getJournal(token,fileId,workspaceId,control);
    const emptySlot=()=>journal.writer==='unclaimed'&&journal.operations.length===0;
    if(!emptySlot())throw new SyncError('This journal is already assigned or contains tasks. Choose an empty partner slot.');
    // Picker grants access to this exact partner file. Test only its empty envelope.
    await this.probeEmptyConditionalWrite(token,fileId,journal,etag,control);
    ({journal,etag}=await this.getJournal(token,fileId,workspaceId,control));
    if(!emptySlot())throw new SyncError('Another device claimed this partner slot. Create a new device file.');
    if(!/^"[^"\r\n]+"$/.test(etag))throw new SyncError('Google did not expose a strong ETag. The partner slot was not claimed.');
    try{await this.raw(token,UPLOAD+encodeURIComponent(fileId)+'?uploadType=media&fields=id',{method:'PATCH',headers:{'Content-Type':'application/json; charset=UTF-8','If-Match':etag},body:JSON.stringify({...journal,writer:deviceId})},control)}catch(error){if(error.status===412)throw new SyncError('Another device changed or claimed this partner slot. Create a new device file.',412);throw error}
    // Do not mutate the private binding until the UI receives confirmed success.
    return {fileId,deviceId,conditionalVerified:true};
  }
  async pull(token,session,control={}){
    const files=sessionFiles(session),logs=[],participants=[];this.lastParticipants=[];
    for(const file of files){active(control);const {journal}=await this.getJournal(token,file.id,session.workspaceId,control);logs.push(journal.operations);participants.push({fileId:file.id,writer:journal.writer})}
    const merged=mergeJournal(...logs);this.lastParticipants=participants;return merged;
  }
  async push(token,session,log,_actor,_uploaded,control={}){
    const files=sessionFiles(session);active(control);const {fileId,deviceId,conditionalVerified}=this.binding||{};
    if(!validId(fileId)||!validId(deviceId))throw new SyncError('This device is read-only. Create its own journal before uploading changes.');
    if(conditionalVerified!==true)throw new SyncError('This device has not verified safe conditional journal writes. Create and verify its own journal first.');
    if(!files.some(file=>file.id===fileId))throw new SyncError('Select this device’s own journal before uploading changes.');
    const {journal,etag}=await this.getJournal(token,fileId,session.workspaceId,control);
    if(journal.writer!==deviceId)throw new SyncError('This journal belongs to another device. Create a new journal; peer journals are read-only.');
    const operations=mergeJournal(journal.operations,log);
    if(stable(operations)===stable(journal.operations))return operations.map(op=>op.id);
    // Weak or inaccessible ETags cannot protect a media replacement. Fail closed.
    if(!/^"[^"\r\n]+"$/.test(etag))throw new SyncError('Google did not expose a strong ETag. Upload is paused to avoid overwriting a journal.');
    const body=JSON.stringify({...journal,operations});
    if(new TextEncoder().encode(body).length>MAX_BYTES)throw new SyncError('The journal reached its 8 MB limit. Upload is paused; local changes were kept.');
    active(control);
    await this.raw(token,UPLOAD+encodeURIComponent(fileId)+'?uploadType=media&fields=id',{method:'PATCH',headers:{'Content-Type':'application/json; charset=UTF-8','If-Match':etag},body},control);
    return operations.map(op=>op.id);
  }
}
