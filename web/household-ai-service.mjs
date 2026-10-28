/* Household AI is an explicit, session-only override. Never persist decrypted
   keys/passphrases, auto-apply shared changes, or include it in task sync. */
import {openHouseholdBundle} from './household-ai-crypto.mjs';
import {HouseholdAIStore} from './household-ai-store.mjs';
export class HouseholdAI {
  constructor({sync,runtime,store,storage=globalThis.localStorage,prefix='tether-household-ai-pin:'}){
    this.sync=sync;this.runtime=runtime;this.store=store||new HouseholdAIStore({transport:sync.transport});this.storage=storage;this.prefix=prefix;this.pending=null;this.generation=0;
  }
  async selected(){const s=await this.sync.state();if(!s.metadata.session)throw Error('Create or join a household first.');if(!this.sync.token)throw Error('Connect Google Drive first.');return s.metadata.session}
  cancel(){this.generation++;this.pending=null}
  lock(){this.cancel();this.runtime.householdAI.lock()}
  async status(){const active=await this.runtime.householdAI.status();return {...active,pending:this.pending?{base_url:this.pending.bundle.base_url,model:this.pending.bundle.model,revision:this.pending.id,changed:this.pending.changed}:null}}
  async versions(){const session=await this.selected(),generation=this.generation;const result=await this.store.read(this.sync.token,session,{isActive:()=>generation===this.generation});return {versions:result.versions.map(v=>({id:v.id,parents:v.parents})),tips:result.tips.map(v=>typeof v==='string'?v:v.id)}}
  async publish(passphrase,{confirmed=false}={}){
    if(!confirmed)throw Error('Confirm uploading the encrypted key to this household first.');
    const generation=this.generation,session=await this.selected(),token=this.sync.token,syncGeneration=this.sync.generation;
    const active=()=>generation===this.generation&&token===this.sync.token&&syncGeneration===this.sync.generation;
    const previous=await this.store.read(token,session,{isActive:active});if(!active())throw Error('Household setup was cancelled.');
    const id=crypto.randomUUID().replaceAll('-','');
    const ciphertext=await this.runtime.householdAI.seal(passphrase,{householdId:session.spreadsheetId,revisionId:id});
    if(!active())throw Error('Household setup was cancelled.');
    if((await this.selected()).spreadsheetId!==session.spreadsheetId)throw Error('The selected household changed. Start sharing again.');
    if(!active())throw Error('Household setup was cancelled.');
    const parents=previous.tips.map(v=>typeof v==='string'?v:v.id);
    await this.store.append(token,session,{id,parents,ciphertext},{isActive:active,confirmed:true});
    if(!active())throw Error('Settings closed after upload. Reopen to check the shared AI setup.');
    // Publishing does not silently change the current device's provider.
    this.runtime.householdAI.lock();return {id};
  }
  async unlock(passphrase,{revisionId}={}){
    this.cancel();const generation=this.generation,session=await this.selected(),token=this.sync.token,syncGeneration=this.sync.generation;
    const active=()=>generation===this.generation&&token===this.sync.token&&syncGeneration===this.sync.generation;
    const remote=await this.store.read(token,session,{isActive:active});if(!active())throw Error('Unlock was cancelled.');
    const tips=remote.tips.map(v=>typeof v==='string'?v:v.id);
    if(!tips.length)throw Error('No shared AI connection yet. Ask the household creator to finish Share household.');
    if(!revisionId&&tips.length!==1)throw Error('The household has conflicting AI settings. Ask its creator to publish the intended connection again.');
    const id=revisionId||tips[0];if(!tips.includes(id))throw Error('Choose a current household AI version.');
    const version=remote.versions.find(v=>v.id===id);if(!version)throw Error('Shared AI version is unavailable.');
    const bundle=await openHouseholdBundle(version.ciphertext,passphrase,{householdId:session.spreadsheetId,revisionId:id});
    if(!active())throw Error('Unlock was cancelled.');
    let old;try{old=JSON.parse(this.storage?.getItem(this.prefix+session.spreadsheetId)||'null')}catch(_){}
    this.pending={id,bundle,householdId:session.spreadsheetId,changed:!!old&&(old.base_url!==bundle.base_url||old.model!==bundle.model||old.revision!==id)};
    return {base_url:bundle.base_url,model:bundle.model,changed:this.pending.changed};
  }
  async confirm({confirmed=false}={}){
    if(!confirmed||!this.pending)throw Error('Review and confirm the household AI provider first.');
    const p=this.pending,generation=this.generation,session=await this.selected();if(generation!==this.generation||this.pending!==p)throw Error('Unlock was cancelled.');if(session.spreadsheetId!==p.householdId){this.cancel();throw Error('The selected household changed. Unlock again.');}
    await this.runtime.householdAI.use(p.bundle,{householdId:p.householdId,revisionId:p.id,confirmed:true,isActive:()=>generation===this.generation&&this.pending===p});
    if(generation!==this.generation||this.pending!==p)throw Error('Unlock was cancelled.');
    // Only non-secret endpoint/model/revision pins persist. No automatic trust.
    try{this.storage?.setItem(this.prefix+p.householdId,JSON.stringify({base_url:p.bundle.base_url,model:p.bundle.model,revision:p.id}))}catch(_){}
    this.pending=null;return {ok:true};
  }
}
