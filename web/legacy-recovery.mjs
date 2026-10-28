/* Deliberate, read-only recovery. Never creates a runtime or resumes old jobs. */
import {exportData} from './portable.mjs';
export async function readLegacy(base,{indexedDB=globalThis.indexedDB}={}){
  const name='tether-chat-web:'+base;
  // Abort creation when absent (also works where indexedDB.databases is unavailable).
  const db=await new Promise((resolve,reject)=>{
    const request=indexedDB.open(name,1);let absent=false;
    request.onupgradeneeded=()=>{absent=true;request.transaction.abort()};
    request.onerror=()=>absent?resolve(null):reject(request.error);
    request.onsuccess=()=>resolve(request.result);
    request.onblocked=()=>reject(Error('Close older tether tabs and try recovery again.'));
  });
  if(!db)return null;
  try{return await new Promise((resolve,reject)=>{
    const tx=db.transaction('state','readonly'),request=tx.objectStore('state').get('data');let state;
    request.onsuccess=()=>{state=request.result};tx.oncomplete=()=>resolve(state||null);
    tx.onabort=tx.onerror=()=>reject(tx.error||Error('Could not read earlier Work storage'));
  })}finally{db.close()}
}
export function recoveryFiles(state,storage=globalThis.localStorage,base='/'){
  const portable=state?{...exportData(state),workspace:'work'}:null;
  const settings=state?.settings||{};
  const privateRecovery={format:'tether-private-work-recovery',version:1,workspace:'work',portable,
    connection:{base_url:settings.base_url,model:settings.model,encrypted_key:settings.encrypted_key},
    draft:storage?.getItem('tether-web-draft:'+base)||'',outbox:storage?.getItem('tether-web-outbox:'+base)||'',
    warning:'Private local recovery only. Contains Work content. Do not upload to shared Home Drive files. Session keys excluded.'};
  return {portable,privateRecovery};
}
export function bindRecovery({base,document,download}){
  const $=id=>document.getElementById(id);let files;
  $('inspectLegacy').onclick=async()=>{try{
    files=recoveryFiles(await readLegacy(base),globalThis.localStorage,base);
    const data=files.portable?.data;
    $('legacyStatus').textContent=data?`Earlier Work: ${data.tasks.length} tasks, ${data.messages.length} messages. Nothing moved, resumed, or shared.`:'No earlier Work task database found. You can still save any retained draft/outbox.';
    $('exportLegacy').hidden=!files.portable;$('exportLegacyPrivate').hidden=false;
  }catch(error){$('legacyStatus').textContent='Recovery could not read storage: '+error.message}};
  const save=(value,name)=>download(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),name);
  $('exportLegacy').onclick=()=>files?.portable&&save(files.portable,'tether-work-backup.json');
  $('exportLegacyPrivate').onclick=()=>files&&save(files.privateRecovery,'tether-private-work-recovery.json');
}
