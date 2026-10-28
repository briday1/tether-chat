/* Durable setup bookkeeping. No OAuth tokens or task data are stored here. */
import {uuid} from './drive-sync-service.mjs';
import {SyncError} from './drive-sync-core.mjs';
const clone=value=>structuredClone(value);
const validId=value=>typeof value==='string'&&/^[A-Za-z0-9_-]{8,200}$/.test(value);
const cleanFile=file=>{if(!validId(file?.id))throw new SyncError('Google did not confirm a valid file ID');return {id:file.id,name:typeof file.name==='string'?file.name.slice(0,200):file.id}};
const stopped=()=>new SyncError('Setup stopped. An already-sent request may have completed; confirmed progress was kept for Resume.',499);
export class HouseholdSetup {
  constructor({transport,localStorage,storageKey,device,activate,locks=globalThis.navigator?.locks}){
    this.transport=transport;this.storage=localStorage;this.key=storageKey;this.device=device;this.activate=activate;this.locks=locks;this.dirty=false;this.generation=0;this.running=false;this.pending=undefined;
  }
  state(){
    if(this.dirty)return this.pending?clone(this.pending):null;
    const raw=this.storage.getItem(this.key);if(!raw){this.pending=null;return null}
    let saved;try{if(raw.length>100000)throw Error();saved=JSON.parse(raw)}catch(_){throw new SyncError('Saved setup progress is unreadable. Review it before starting another household.')}
    const allowed=new Set(['version','id','device','inflight','kind','step','name','deviceName','folder','own','partner','files','slotId','binding']);
    if(!saved||typeof saved!=='object'||Array.isArray(saved)||Object.keys(saved).some(key=>!allowed.has(key))||saved.version!==1||saved.device!==this.device||!validId(saved.id)||!['create','join','add'].includes(saved.kind)||!['folder','own','verify','partner','claim','activate','done'].includes(saved.step)||![null,'folder','own','verify','partner','claim','activate'].includes(saved.inflight))throw new SyncError('Saved setup belongs to a different device or version, or has invalid fields.');
    for(const key of ['folder','own','partner'])if(saved[key])saved[key]=cleanFile(saved[key]);
    if(saved.files){if(!Array.isArray(saved.files)||saved.files.length>50)throw new SyncError('Invalid saved household files');saved.files=saved.files.map(cleanFile)}
    if(saved.binding&&(Object.keys(saved.binding).sort().join(',')!=='conditionalVerified,deviceId,fileId'||!validId(saved.binding.fileId)||saved.binding.deviceId!==this.device||saved.binding.conditionalVerified!==true))throw new SyncError('Invalid saved device binding');
    if(['create','add'].includes(saved.kind)&&(typeof saved.name!=='string'||!saved.name.trim()||saved.name.length>80||typeof saved.deviceName!=='string'||saved.deviceName.length>60))throw new SyncError('Invalid saved household name');
    if(saved.kind==='join'&&(!validId(saved.slotId)||!saved.files?.some(file=>file.id===saved.slotId)))throw new SyncError('Invalid saved partner slot');
    if(saved.step!=='folder'&&!saved.folder)throw new SyncError('Saved setup is missing its confirmed folder');
    if(['verify','partner'].includes(saved.step)&&!saved.own)throw new SyncError('Saved setup is missing its confirmed device file');
    if(['activate','done'].includes(saved.step)&&(!saved.binding||!saved.files))throw new SyncError('Saved setup is missing its activation details');
    this.pending=saved;return clone(saved);
  }
  persist(value){
    // Keep a confirmed response in memory even if local storage becomes full.
    this.pending=clone(value);this.dirty=true;this.storage.setItem(this.key,JSON.stringify(value));this.dirty=false;
  }
  stop(){this.generation++}
  abandon(){this.stop();let previous;try{previous=this.state()}catch(_){previous=null}this.storage.removeItem(this.key);this.pending=null;this.dirty=false;return previous}
  begin(data){if(this.state())throw new SyncError('Setup progress already exists. Resume it or explicitly abandon it first.');this.persist({version:1,id:uuid(),device:this.device,inflight:null,...data})}
  create(token,{name,deviceName='My device'}={}){
    if(typeof name!=='string'||!name.trim())throw new SyncError('Give your household a name.');
    this.begin({kind:'create',step:'folder',name:name.trim().slice(0,80),deviceName:String(deviceName||'My device').trim().slice(0,60)});return this.resume(token);
  }
  add(token,{folder,deviceName='My device'}={}){
    const selected=cleanFile(folder);this.begin({kind:'add',step:'own',folder:selected,name:selected.name.slice(0,80),deviceName:String(deviceName||'My device').trim().slice(0,60)});return this.resume(token);
  }
  join(token,{folder,files,slotId}={}){
    if(!Array.isArray(files)||files.length<2||files.length>50||!validId(slotId)||!files.some(file=>file.id===slotId))throw new SyncError('Select the household files and an empty partner slot.');
    this.begin({kind:'join',step:'claim',folder:cleanFile(folder),files:files.map(cleanFile),slotId});return this.resume(token);
  }
  async resume(token){
    if(this.running)throw new SyncError('Setup is already running.');
    const generation=this.generation;
    if(this.locks)return this.locks.request('tether-household-setup:'+this.key,{ifAvailable:true},lock=>{if(!lock)throw new SyncError('Household setup is running in another window.');if(generation!==this.generation)throw stopped();return this.runResume(token)});
    return this.runResume(token);
  }
  async runResume(token){
    if(this.running)throw new SyncError('Setup is already running.');if(!token)throw new SyncError('Connect Google Drive before resuming setup.',401);
    const initial=this.state();if(!initial)throw new SyncError('There is no saved setup to resume.');
    const generation=this.generation,identity=initial.id,active=()=>this.generation===generation&&this.pending?.id===identity;
    const check=()=>{const current=this.state();if(!active()||current?.id!==identity)throw stopped()};
    const control={isActive:active};
    this.running=true;
    try{
      while(true){
        check();const s=this.state();
        if(s.inflight&&['folder','own','partner'].includes(s.inflight))throw new SyncError('The outcome of the last Drive creation is unconfirmed. Tether will not repeat it automatically. Check Drive, or explicitly abandon this setup before starting again.');
        const step=async(name,request,completed)=>{
          check();this.persist({...s,inflight:name});let result;
          try{result=await request()}catch(error){
            // An explicit client error means this creation was refused. Network/5xx
            // outcomes remain uncertain and are never automatically repeated.
            if(active()&&error.status>=400&&error.status<500&&error.status!==499)this.persist({...s,inflight:null});
            throw error;
          }
          if(this.state()?.id!==identity)throw stopped(); // Explicitly abandoned while request was in flight.
          this.persist({...s,...completed(result),inflight:null});check();
        };
        if(s.kind==='create'&&s.step==='folder'){
          await step('folder',()=>this.transport.request(token,'https://www.googleapis.com/drive/v3/files?fields=id,name',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'Tether · '+s.name,mimeType:'application/vnd.google-apps.folder'})}),folder=>({folder:cleanFile(folder),step:'own'}));
        }else if(['create','add'].includes(s.kind)&&s.step==='own'){
          await step('own',()=>this.transport.createJournal(token,s.folder.id,s.folder.id,this.device,{...control,name:'Tether · '+s.name+' · '+s.deviceName+'.json'}),own=>({own:cleanFile(own),step:'verify'}));
        }else if(['create','add'].includes(s.kind)&&s.step==='verify'){
          // Confirmed local creation can be revalidated after a page reload.
          await step('verify',()=>this.transport.resumeClaim(token,s.own.id,s.folder.id,this.device,control),binding=>s.kind==='add'?{binding,files:[s.own],step:'activate'}:{binding,step:'partner'});
        }else if(s.kind==='create'&&s.step==='partner'){
          await step('partner',()=>this.transport.createPartnerSlot(token,s.folder.id,s.folder.id,{...control,name:'Tether · '+s.name+' · Partner device.json'}),partner=>({partner:cleanFile(partner),files:[s.own,cleanFile(partner)],step:'activate'}));
        }else if(s.kind==='join'&&s.step==='claim'){
          await step('claim',async()=>{
            const {journal}=await this.transport.readJournal(token,s.slotId,s.folder.id,control);check();
            if(journal.operations.length)throw new SyncError('This partner file already contains tasks. Setup will not replace it.');
            if(journal.writer===this.device)return this.transport.resumeClaim(token,s.slotId,s.folder.id,this.device,control);
            if(journal.writer==='unclaimed')return this.transport.claimSlot(token,s.slotId,s.folder.id,this.device,control);
            throw new SyncError('Another device owns this partner file. Choose a different empty slot.');
          },binding=>({binding,step:'activate'}));
        }else if(s.step==='activate'){
          await step('activate',()=>this.activate(clone(s.folder),clone(s.files),clone(s.binding),control),()=>({step:'done'}));
        }else if(s.step==='done'){
          this.storage.removeItem(this.key);this.pending=null;this.dirty=false;return {folder:s.folder,files:s.files,binding:s.binding};
        }else throw new SyncError('Saved setup has an unsupported step. No Drive changes were made.');
      }
    }finally{this.running=false}
  }
}
