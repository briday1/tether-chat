import {buildHouseholdInvite} from './household-invite.mjs';
import {HouseholdSetup} from './drive-setup.mjs';
const root=document.getElementById('sharingSettings');
const $=id=>root.querySelector('#'+id)||document.getElementById(id),host=window.top;
if(window.TETHER_CONFIG?.product!=='tether-home')throw Error('Household sharing is available only in tether-home.');
const fetcher=window.fetch.bind(window),apiBase=window.TETHER_CONFIG.base+'api';
const local=async(method,body)=>{const response=await fetcher(apiBase+'/drive-sync/local',{method,headers:{'Content-Type':'application/json','X-Tether-Workspace':'home'},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok){const error=Error(result.detail||'Local sync failed');error.status=response.status;throw error}return result};
const storagePrefix='tether-home-drive:'+apiBase+':';
const service=await host.tetherHomeSyncReady;
const householdAI=await host.tetherHouseholdAIReady;
const nameKey="tether-household-name:"+window.TETHER_CONFIG.base;
try{$("householdName").value=localStorage.getItem(nameKey)||"Our Home"}catch(_){}
$("householdName").addEventListener("change",()=>{try{localStorage.setItem(nameKey,$("householdName").value.trim())}catch(_){}});
let busy=false,picker=null,uiGeneration=0;
const pendingDialogs=new Set();
function dialogResult(start){return new Promise((resolve,reject)=>{
  const finish=(fn,value)=>{pendingDialogs.delete(cancel);fn(value)};
  const cancel=()=>finish(reject,Error('Setup paused. Reopen Settings to continue.'));pendingDialogs.add(cancel);
  try{start(value=>finish(resolve,value),error=>finish(reject,error))}catch(error){finish(reject,error)}
})}
const setup=new HouseholdSetup({transport:service.transport,localStorage,storageKey:storagePrefix+'pending-sheet-setup',activate:activateHousehold});
host.tetherHomeSetup=setup;
const sheetURL=id=>'https://docs.google.com/spreadsheets/d/'+encodeURIComponent(id)+'/edit';
const invitation=()=>host.tetherHouseholdInvite;
const status=text=>{$('syncStatus').textContent=text;if(/Google|copied|Paused|Reconnect|Invitation|Setup/.test(text))$('householdMessage').textContent=text;};
async function show(){
  const s=await local('GET'),session=s.metadata.session,pending=setup.state();
  const ai=await householdAI.status();
  $('householdAISection').hidden=!session;
  $('householdUnlock').hidden=ai.active;
  $('lockHouseholdAI').hidden=!ai.active;
  $('householdPersonalProvider').hidden=ai.active;
  $('householdAIOverview').textContent=ai.active?'Using the shared household AI connection for this session.':ai.personal.has_key?'AI connection ready. Use this household yourself, or share it below.':'Set up your AI connection, or open a household invitation to use a shared one.';
  $('householdAIReview').hidden=!ai.pending;
  if(ai.pending)$('householdProviderReview').textContent=(ai.pending.changed?'This shared connection differs from the one previously approved. ':'')+'Provider: '+ai.pending.base_url+' · Model: '+ai.pending.model+'. Anyone who knows the passphrase can publish changes; confirm this address with the household creator.';
  if(ai.active)$('sharedAIStatus').textContent='Unlocked for this session. Closing tether or locking it removes the decrypted household key from memory.';
  const invite=invitation(),inviteError=host.tetherInviteError;
  $('householdInvitation').hidden=!invite&&!inviteError;
  $('invitationTitle').textContent=invite?'Join '+invite.name:inviteError||'';
  $('invitationHelp').textContent=invite?(session?(session.spreadsheetId===invite.id?'This device is already connected to this household.':'This device is connected to another household. Disconnect it first; local tasks are kept.'): 'Connect your Google account, review the sharing consent below, then join. '+Object.keys(s.records||{}).length+' local Home records will be merged and shared. The name in this link is supplied by its sender; confirm the Sheet in Google.') : 'Ask the sender for a new household invitation link.';
  $('joinInvitation').disabled=!invite||!!session;
  $('pendingSetup').hidden=!pending;$('setupProgress').textContent=pending?'Saved setup: '+pending.step+(pending.inflight?' (last request needs checking)':''):'';
  $('pendingSheet').hidden=!pending?.household;if(pending?.household)$('pendingSheet').href=sheetURL(pending.household.id);
  $('householdStatus').textContent=session?'Household: '+(session.householdName||'Shared Home'):'No household connected';
  $('householdChoices').hidden=!!session||!!invite;$('newHousehold').hidden=!!session||!!invite;$('sharingLinks').hidden=!session;
  if(session){$('shareHousehold').href=sheetURL(session.spreadsheetId);$('householdName').value=session.householdName?.replace(/^Tether · /,'')||$('householdName').value;}
  $('connectionStatus').textContent=session?'This device is connected to the household Sheet. Other people must receive access and connect the same Sheet; this status does not confirm their connection.':'';
  $('disconnect').disabled=!session;$('sync').disabled=!service.token||!session;
  status(service.status+(s.metadata.lastSync?'\nLast sync: '+new Date(s.metadata.lastSync).toLocaleString():''));
  $('conflicts').replaceChildren();for(const conflict of s.metadata.conflicts||[]){
    const box=document.createElement('div');box.className='conflict';const title=document.createElement('p');title.textContent=(s.records[conflict.key]?.title||conflict.key)+' · '+(conflict.field==='$exists'?'Delete or keep':conflict.field);box.append(title);
    for(const c of new Map(conflict.choices.map(c=>[JSON.stringify(c.value),c])).values()){
      const button=document.createElement('button');button.textContent=conflict.field==='$exists'?(c.value?'Keep task':'Delete task'):typeof c.value==='string'?c.value:JSON.stringify(c.value);button.onclick=()=>run(()=>service.choose(conflict.key,conflict.field,c.value));box.append(button);
    }$('conflicts').append(box);
  }
}
window.addEventListener('tether-provider-changed',()=>show().catch(()=>{}));
service.changed=()=>show().catch(error=>status(error.message));
async function run(fn){if(busy)return;busy=true;$('householdMessage').textContent='';try{await fn();await show()}catch(error){service.status=error.message;await show().catch(()=>{});status(error.message);$('householdMessage').textContent=error.message}finally{busy=false}}
function script(src){return new Promise((resolve,reject)=>{const node=document.createElement('script');node.src=src;node.onload=resolve;node.onerror=()=>reject(Error('Could not load Google sign-in. Check your connection.'));document.head.append(node)})}
async function libraries(){if(!window.google?.accounts?.oauth2)await script('https://accounts.google.com/gsi/client');if(!window.gapi)await script('https://apis.google.com/js/api.js');if(!window.google?.picker)await new Promise((resolve,reject)=>gapi.load('picker',{callback:resolve,onerror:()=>reject(Error('Could not load Google Picker'))}))}
$('origin').textContent='Allowed JavaScript origin: '+location.origin;
for(const field of ['clientId','projectNumber','pickerKey'])try{$(field).value=localStorage.getItem(storagePrefix+field)||''}catch(_){}
try{const defaults=await (await fetcher(new URL('./drive-config.json',import.meta.url))).json();for(const field of ['clientId','projectNumber','pickerKey'])if(!$(field).value&&typeof defaults[field]==='string')$(field).value=defaults[field]}catch(_){}
const SCOPE='https://www.googleapis.com/auth/drive.file';
$('scopeDisclosure').textContent='Tether requests access only to Drive files you select or that it creates. It cannot browse the contents of your whole Drive.';
$('connect').onclick=()=>run(async()=>{
  const generation=uiGeneration;
  const clientId=$('clientId').value.trim(),project=$('projectNumber').value.trim(),key=$('pickerKey').value.trim();
  if(!/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(clientId)||!/^\d+$/.test(project)||!key)throw Error('Complete the public app setup: OAuth client ID, project number and restricted Picker browser key.');
  if(!window.google?.accounts?.oauth2||!window.google?.picker){await libraries();service.status='Google sign-in is ready. Click Connect Google Drive again.';return;}
  for(const field of ['clientId','projectNumber','pickerKey'])localStorage.setItem(storagePrefix+field,$(field).value.trim());
  await dialogResult((resolve,reject)=>{const auth=google.accounts.oauth2.initTokenClient({client_id:clientId,scope:SCOPE,callback:result=>{if(generation!==uiGeneration)return reject(Error('Google connection was paused.'));if(result.error)return reject(Error(result.error));if(!google.accounts.oauth2.hasGrantedAllScopes(result,SCOPE))return reject(Error('The selected-file Drive permission was not granted.'));service.authorize(result.access_token,Number(result.expires_in));resolve()},error_callback:()=>reject(Error('Google sign-in was cancelled or blocked.'))});auth.requestAccessToken({prompt:''})});
  const s=await local('GET');service.status='Google connected';if(s.metadata.session)await service.start(service.token)
});
function chooseHousehold(invite=null){
  if(!service.token)throw Error('Connect Google Drive first.');
  return dialogResult(resolve=>{
    const view=new google.picker.DocsView(google.picker.ViewId.DOCS).setMode(google.picker.DocsViewMode.LIST).setMimeTypes('application/vnd.google-apps.spreadsheet');
    if(invite)view.setFileIds(invite.id).setLabel('Invited household');
    const builder=new google.picker.PickerBuilder().addView(view).setOAuthToken(service.token).setDeveloperKey($('pickerKey').value.trim()).setAppId($('projectNumber').value.trim()).setOrigin(location.origin).setCallback(data=>{
      if(data.action===google.picker.Action.PICKED){picker?.dispose();picker=null;resolve(data.docs?.[0]||null)}else if(data.action===google.picker.Action.CANCEL){picker?.dispose();picker=null;resolve(null)}
    });picker=builder.build();picker.setVisible(true);
  });
}
function requireSetup(){if(!service.token)throw Error('Connect your Google account first.');if(!$('consent').checked)throw Error('Confirm which Home data you want to share.');}
async function activateHousehold(household,control={isActive:()=>true}){
  const check=()=>{if(!control.isActive())throw Error('Setup paused. Resume when ready.');};check();
  const session={mode:'selected-sheet',spreadsheetId:household.id,workspaceId:household.id,sheetId:household.sheetId,householdName:household.name};
  const current=await local('GET');check();
  if(current.metadata.session){if(current.metadata.session.workspaceId!==household.id)throw Error('Disconnect the existing household before connecting another.');}
  else{await service.configure(session,{publishExisting:true});check();}
  await service.start(service.token);check();
}
$('createHousehold').onclick=()=>run(async()=>{
  requireSetup();const generation=uiGeneration,current=await local('GET');if(generation!==uiGeneration)throw Error('Setup paused.');if(current.metadata.session)throw Error('Disconnect the existing household first.');
  service.stop();await setup.create(service.token,{name:$('householdName').value.trim()});
});
$('joinHousehold').onclick=()=>run(async()=>{
  requireSetup();const generation=uiGeneration,current=await local('GET');if(generation!==uiGeneration)throw Error('Setup paused.');if(current.metadata.session)throw Error('Disconnect the existing household first.');
  const file=await chooseHousehold();if(generation!==uiGeneration)throw Error('Setup paused.');if(!file)return;
  service.stop();await setup.join(service.token,{id:file.id});
});
$('resumeSetup').onclick=()=>run(async()=>{requireSetup();await setup.resume(service.token)});
$('abandonSetup').onclick=()=>run(async()=>{if(confirm('Forget pending setup? Existing Sheets and local data are kept. Check Drive before creating another household.'))setup.abandon()});
$('joinInvitation').onclick=()=>run(async()=>{
  requireSetup();const invite=invitation();if(!invite)throw Error('Open a valid household invitation first.');
  const generation=uiGeneration,current=await local('GET');
  if(current.metadata.session)throw Error('Disconnect the existing household before joining another. Local tasks are kept.');
  if(setup.state())throw Error('Resume or forget the pending setup before joining this invitation.');
  if(generation!==uiGeneration)throw Error('Setup paused.');
  const file=await chooseHousehold(invite);if(generation!==uiGeneration)throw Error('Setup paused.');
  if(!file){service.status='Invitation kept. If no file appears, check your Google account and ask the sender to grant Editor access, then try again.';return;}
  if(file.id!==invite.id)throw Error('That is not the invited household. Try again and select the invited Sheet; nothing was joined.');
  service.stop();await setup.join(service.token,{id:invite.id});
});
$('dismissInvitation').onclick=()=>{pauseSetup();host.tetherDismissInvite();const url=new URL(location.href);url.hash='';history.replaceState({},'',url);show()};
$('copyInvite').onclick=()=>run(async()=>{const s=await local('GET');if(!s.metadata.session)throw Error('Create or join a household first.');await navigator.clipboard.writeText(buildHouseholdInvite(new URL(window.TETHER_CONFIG.base,location.origin),{id:s.metadata.session.spreadsheetId,name:s.metadata.session.householdName||'Shared Home'}));service.status='Household invitation copied. Give Editor access in Drive, send this invitation, and share the household AI passphrase separately. The invitation contains no key or passphrase.';});
$('sync').onclick=()=>run(()=>service.sync({force:true}));$('pause').onclick=()=>{uiGeneration++;setup.stop();service.stop();service.status='Paused; local edits are safe';show()};
$('disconnect').onclick=()=>run(async()=>{if(confirm('Stop syncing this household? Local tasks and the shared Sheet are kept.')){uiGeneration++;setup.stop();householdAI.lock();await service.disconnect()}});

$('publishHouseholdKey').onclick=()=>run(async()=>{
  const passphrase=$('householdSharePassphrase').value,again=$('householdSharePassphraseAgain').value;
  $('householdSharePassphrase').value='';$('householdSharePassphraseAgain').value='';
  const confirmed=$('shareHouseholdKeyConsent').checked;$('shareHouseholdKeyConsent').checked=false;
  if(passphrase!==again)throw Error('The household passphrases do not match.');
  await householdAI.publish(passphrase,{confirmed});
  $('sharedAIStatus').textContent='AI connection encrypted and shared. Give the passphrase separately, then copy the household invitation.';
});
$('unlockHouseholdAI').onclick=()=>run(async()=>{
  const passphrase=$('householdUnlockPassphrase').value;$('householdUnlockPassphrase').value='';$('trustHouseholdProvider').checked=false;
  await householdAI.unlock(passphrase);$('sharedAIStatus').textContent='Review the provider address below before using the shared key.';
});
$('useHouseholdAI').onclick=()=>run(async()=>{
  await householdAI.confirm({confirmed:$('trustHouseholdProvider').checked});$('trustHouseholdProvider').checked=false;await window.tetherLoadSettings?.();
});
$('lockHouseholdAI').onclick=()=>run(async()=>{householdAI.lock();$('sharedAIStatus').textContent='Household AI locked. Your own saved connection is unchanged.';await window.tetherLoadSettings?.()});

const pauseSetup=()=>{uiGeneration++;setup.stop();householdAI.cancel();for(const id of ['householdUnlockPassphrase','householdSharePassphrase','householdSharePassphraseAgain'])$(id).value='';$('trustHouseholdProvider').checked=false;$('shareHouseholdKeyConsent').checked=false;for(const cancel of [...pendingDialogs])cancel();picker?.dispose();picker=null};
window.addEventListener('pagehide',pauseSetup);
// Dismissing Settings cancels unfinished sign-in/setup, not an established sync.
const settings=root.closest('#settings');
if(settings)new MutationObserver(()=>{if(settings.classList.contains('hidden'))pauseSetup()}).observe(settings,{attributes:true,attributeFilter:['class']});
await show().catch(error=>status(error.message));
