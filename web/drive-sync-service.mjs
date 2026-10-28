import {mergeJournal,makeChanges,materialize,resolve,SyncError,stable} from './drive-sync-core.mjs';
export const uuid=()=>crypto.randomUUID().replaceAll('-','');
// Retain causal history locally while disconnected, without an active session,
// credentials, connection generation, or recursively nested detached copies.
function detachedHistory(metadata){
  const source=metadata.session?metadata:metadata.detached?.session?metadata.detached:null;
  if(!source)return {};
  const kept={};for(const key of ['log','baseline','actor','uploaded','conflicts','lastSync'])if(Object.hasOwn(source,key))kept[key]=structuredClone(source[key]);
  kept.session={};for(const key of ['mode','workspaceId','spreadsheetId','sheetId','householdName'])if(Object.hasOwn(source.session,key))kept.session[key]=source.session[key];
  if(Array.isArray(source.session.files))kept.session.files=source.session.files.map(file=>({id:file.id,...(typeof file.name==='string'?{name:file.name}:{})}));
  return {detached:kept};
}
export class HomeSync {
  constructor({local,transport,actor=uuid(),changed=()=>{},locks=globalThis.navigator?.locks,scheduler=globalThis}){this.scheduler=scheduler;this.local=local;this.transport=transport;this.actor=actor;this.changed=changed;this.locks=locks;this.running=false;this.generation=0;this.token='';this.timer=null;this.status='Disconnected';}
  async state(){return this.local('GET')}
  async commit(s,records,metadata){return this.local('POST',{expected:s.records,records,metadata,expected_revision:s.revision})}
  async configure(settings,{publishExisting=false}={}){
    const s=await this.state();if(s.metadata.session&&stable(s.metadata.session)!==stable(settings))throw new SyncError('Disconnect this shared Home before choosing another.');
    if(!s.metadata.session){
      const detached=detachedHistory(s.metadata).detached;
      const resume=typeof settings?.workspaceId==='string'&&detached?.session?.workspaceId===settings.workspaceId;
      if((resume||Object.keys(s.records).length)&&!publishExisting)throw new SyncError('Confirm sharing the existing Home tasks, notes, and changes first.');
      let session=structuredClone(settings);
      if(resume&&Array.isArray(detached.session.files)&&Array.isArray(settings.files))session.files=[...new Map([...detached.session.files,...settings.files].map(file=>[file.id,file])).values()];
      const history=resume?detached:{actor:this.actor,log:[],baseline:{},conflicts:[],uploaded:[]};
      await this.commit(s,s.records,{...history,session,connection:uuid()});
    }
  }
  async disconnect(){
    this.stop();this.token='';
    // A local edit or an already-started commit may race the disconnect CAS.
    for(let attempt=0;attempt<5;attempt++){
      const s=await this.state();try{await this.commit(s,s.records,detachedHistory(s.metadata));break}catch(error){if(error.status!==409||attempt===4)throw error}
    }
    this.status='Disconnected; local Home data was kept';this.changed(this);
  }
  start(token){this.stop();this.token=token;this.timer=this.scheduler.setInterval(()=>this.sync().catch(()=>{}),30000);return this.sync({force:true})}
  stop(){this.scheduler.clearInterval(this.timer);this.timer=null;this.generation++}
  async sync({force=false}={}){
    if(Date.now()<(this.transport.notBefore||0)&&(!force||this.transport.retryAfterMs))return;
    if(this.running)return;this.running=true;
    const generation=this.generation,token=this.token,active=()=>generation===this.generation&&token===this.token;
    const run=async()=>{
      let s=await this.state();if(!active())return;if(!s.metadata.session||!token)throw new SyncError('Connect Google Drive to sync.',401);
      const session=s.metadata.session,connection=s.metadata.connection||uuid(),actor=s.metadata.actor||this.actor;
      // Persist local edits before the first network request. Offline edits remain in the database.
      let log=mergeJournal(s.metadata.log||[]),op=makeChanges(log,s.metadata.baseline||{},s.records,actor,uuid());
      if(op)log=mergeJournal(log,[op]);
      s=await this.commit(s,s.records,{...s.metadata,connection,actor,log,baseline:s.records});if(!active())return;
      const remote=await this.transport.pull(token,session,{isActive:active});if(!active())return;
      log=mergeJournal(log,remote);
      const merged=materialize(log,s.records);
      // CAS protects edits made while Drive requests were in flight. A race retries next cycle.
      s=await this.commit(s,merged.records,{...s.metadata,log,baseline:merged.records,conflicts:merged.conflicts});if(!active())return;
      const published=await this.transport.push(token,session,log,actor,s.metadata.uploaded||[],{isActive:active});if(!active())return;
      // Read again: a local edit can occur during upload and must not be replaced.
      s=await this.state();if(!active()||s.metadata.connection!==connection||stable(s.metadata.session)!==stable(session))return;
      await this.commit(s,s.records,{...s.metadata,uploaded:[...new Set([...(s.metadata.uploaded||[]),...published])],lastSync:new Date().toISOString()});if(!active())return;
      const acknowledged=new Set(published),queued=log.filter(op=>!acknowledged.has(op.id)).length;
      this.status=merged.conflicts.length?`${merged.conflicts.length} conflict(s) need a choice`:queued?`${queued} change(s) queued; continuing safely`:'Synced';this.changed(this);
    };
    try{if(this.locks)await this.locks.request('tether-home-drive-sync',{ifAvailable:true},lock=>lock?run():undefined);else await run()}
    catch(error){
      if(!active())return;
      if(error.status===401){this.token='';this.stop();this.status='Reconnect Google Drive. Your local changes are safe.'}else if(error.status===409)this.status='Home changed while syncing; retrying safely';else this.status=error.message||'Sync paused; your local changes are safe';this.changed(this);throw error;
    }
    finally{this.running=false}
  }
  async choose(key,field,value){
    const generation=this.generation,s=await this.state();if(generation!==this.generation)return;
    if(!s.metadata.session)throw new SyncError('Connect this shared Home before resolving a conflict.');
    const actor=s.metadata.actor||this.actor;
    let log=mergeJournal(s.metadata.log||[]);
    // Capture unrelated edits before materializing the user's conflict choice.
    const local=makeChanges(log,s.metadata.baseline||{},s.records,actor,uuid());if(local)log=mergeJournal(log,[local]);
    const op=resolve(log,key,field,value,actor,uuid()),next=mergeJournal(log,[op]),merged=materialize(next,s.records);
    await this.commit(s,merged.records,{...s.metadata,actor,log:next,baseline:merged.records,conflicts:merged.conflicts});if(generation!==this.generation)return;return this.sync({force:true});
  }
}
