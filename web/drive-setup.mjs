/* Durable setup intent only: no OAuth tokens, task data, or device ownership slots. */
import {uuid} from './drive-sync-service.mjs';
import {SyncError} from './drive-sync-core.mjs';
const clone=value=>structuredClone(value);
const validId=value=>typeof value==='string'&&/^[A-Za-z0-9_-]{8,200}$/.test(value);
const stopped=()=>new SyncError('Setup stopped. Confirmed progress was kept for Resume.',499);
function household(value){
  if(!validId(value?.id)||!Number.isSafeInteger(value.sheetId)||value.sheetId<0||typeof value.name!=='string'||!value.name.trim()||value.name.length>200)throw new SyncError('Google did not confirm a valid household Sheet');
  return {id:value.id,name:value.name,sheetId:value.sheetId};
}
function validate(value){
  const allowed=['version','id','kind','step','inflight','name','selectedId','household'];
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!allowed.includes(k))||value.version!==2||!validId(value.id)||!['create','join'].includes(value.kind)||!['request','activate','done'].includes(value.step)||![null,'create','inspect','activate'].includes(value.inflight))throw new SyncError('Saved setup has invalid fields or an unsupported version. Review or explicitly abandon it.');
  if(value.kind==='create'&&(typeof value.name!=='string'||!value.name.trim()||value.name.length>80))throw new SyncError('Invalid saved household name');
  if(value.kind==='join'&&!validId(value.selectedId))throw new SyncError('Invalid selected household ID');
  if(value.household)value.household=household(value.household);
  if(value.step!=='request'&&!value.household)throw new SyncError('Saved setup is missing its confirmed household');
  if(value.kind==='join'&&value.household&&value.household.id!==value.selectedId)throw new SyncError('Selected household changed unexpectedly');
  return value;
}
export class HouseholdSetup {
  constructor({transport,localStorage,storageKey,activate,locks=globalThis.navigator?.locks}){
    this.transport=transport;this.storage=localStorage;this.key=storageKey;this.activate=activate;this.locks=locks;this.generation=0;this.running=false;this.dirty=false;this.pending=null;
  }
  read(){
    const raw=this.storage.getItem(this.key);if(!raw)return null;
    if(raw.length>8000)throw new SyncError('Saved setup is oversized');
    let parsed;try{parsed=JSON.parse(raw)}catch(_){throw new SyncError('Saved setup is unreadable. Review it before starting another household.')}
    return validate(parsed);
  }
  state(){return clone(this.dirty?this.pending:this.read())}
  persist(value){this.pending=clone(value);this.dirty=true;this.storage.setItem(this.key,JSON.stringify(value));this.dirty=false}
  stop(){this.generation++}
  abandon(){this.stop();let previous;try{previous=this.state()}catch(_){previous=null}this.storage.removeItem(this.key);this.pending=null;this.dirty=false;return previous}
  create(token,{name}={}){
    if(typeof name!=='string'||!name.trim()||name.trim().length>80)throw new SyncError('Give your household a name of at most 80 characters.');
    return this.execute(token,{kind:'create',name:name.trim()});
  }
  join(token,{id}={}){if(!validId(id))throw new SyncError('Select a valid household Sheet.');return this.execute(token,{kind:'join',selectedId:id})}
  resume(token){return this.execute(token)}
  async execute(token,intent){
    if(this.running)throw new SyncError('Setup is already running.');
    if(!token)throw new SyncError('Connect Google Drive before setup.',401);
    if(!this.locks?.request)throw new SyncError('This browser cannot safely coordinate setup across tabs. Use a browser with Web Locks.');
    const generation=this.generation;this.running=true;
    try{return await this.locks.request('tether-household-setup:'+this.key,{ifAvailable:true},async lock=>{
      if(!lock)throw new SyncError('Household setup is running in another window.');
      if(generation!==this.generation)throw stopped();
      if(intent){if(this.state())throw new SyncError('Setup progress already exists. Resume it or explicitly abandon it first.');this.persist({version:2,id:uuid(),step:'request',inflight:null,...intent})}
      if(this.dirty){const saved=this.read();if((saved&&saved.id!==this.pending.id)||(!saved&&this.pending.step!=='request'))throw stopped();this.persist(this.pending)}
      const initial=this.state();if(!initial)throw new SyncError('There is no saved setup to resume.');
      const identity=initial.id;
      const active=()=>{try{return generation===this.generation&&this.read()?.id===identity}catch(_){return false}};
      const check=()=>{if(!active())throw stopped()};const control={isActive:active};
      while(true){
        check();const s=this.state();
        if(s.step==='request'){
          if(s.inflight==='create')throw new SyncError('The last creation outcome is unconfirmed. It will not be repeated automatically. Inspect Google Drive, then explicitly abandon this setup and join the existing Sheet if it was created.');
          const action=s.kind==='create'?'create':'inspect';this.persist({...s,inflight:action});
          // Every creation error is conservatively ambiguous: a helper may have completed
          // an earlier remote step before reporting an error. Never automatically repeat.
          const result=s.kind==='create'?await this.transport.createHousehold(token,s.name,control):await this.transport.inspectHousehold(token,s.selectedId,control);
          const confirmed=household(result);
          if(s.kind==='join'&&confirmed.id!==s.selectedId)throw new SyncError('Google returned a different selected household');
          if(this.read()?.id!==identity)throw stopped();
          this.persist({...s,household:confirmed,step:'activate',inflight:null});check();
        }else if(s.step==='activate'){
          this.persist({...s,inflight:'activate'});await this.activate(clone(s.household),control);
          if(this.read()?.id!==identity)throw stopped();
          this.persist({...s,step:'done',inflight:null});check();
        }else if(s.step==='done'){
          check();this.storage.removeItem(this.key);this.pending=null;this.dirty=false;return clone(s.household);
        }
      }
    })}finally{this.running=false}
  }
}
