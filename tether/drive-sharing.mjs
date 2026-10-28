import {HomeSync,uuid} from './drive-sync-service.mjs';
import {DriveJournals} from './drive-journals.mjs';
import {HouseholdSetup} from './drive-setup.mjs';
const $=id=>document.getElementById(id),browser=!!window.TETHER_CONFIG,host=browser?window.top:window;
const fetcher=window.fetch.bind(window),apiBase=browser?window.TETHER_CONFIG.base+'api':'/api';
const local=async(method,body)=>{const response=await fetcher(apiBase+'/drive-sync/local',{method,headers:{'Content-Type':'application/json','X-Tether-Workspace':'home'},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok){const error=Error(result.detail||'Local sync failed');error.status=response.status;throw error}return result};
const storagePrefix='tether-home-drive:'+apiBase+':';
let device;try{device=localStorage.getItem(storagePrefix+'device');if(!device){device=uuid();localStorage.setItem(storagePrefix+'device',device)}}catch(_){throw Error('Allow local browser storage before connecting Drive.')}
const getBinding=workspace=>{try{const binding=JSON.parse(localStorage.getItem(storagePrefix+'writer:'+workspace)||'null');return binding?.deviceId===device&&binding.conditionalVerified===true?binding:null}catch(_){return null}};
const service=host.tetherHomeSync||(host.tetherHomeSync=new HomeSync({local,transport:new DriveJournals(fetcher),actor:device}));
let busy=false,selectedFolder=null,picker=null,uiGeneration=0;
const setup=new HouseholdSetup({transport:service.transport,localStorage,storageKey:storagePrefix+'pending-setup',device,activate:activateHousehold});
host.tetherHomeSetup=setup;
const status=text=>$('syncStatus').textContent=text;
async function show(){
  const s=await local('GET'),session=s.metadata.session;
  const pendingSetup=setup.state();$('pendingSetup').hidden=!pendingSetup;$('setupProgress').textContent=pendingSetup?'Saved setup: '+pendingSetup.step+(pendingSetup.inflight?' (last request needs checking)':''):'';
  if(session){selectedFolder={id:session.folderId,name:session.folderName||'Shared Home'};service.transport.binding=getBinding(session.workspaceId)}
  $('folderStatus').textContent=selectedFolder?'Household: '+selectedFolder.name:'No household connected';$('householdChoices').hidden=!!session;$('newHousehold').hidden=!!session;$('sharingLinks').hidden=!session;if(session)$('shareFolder').href='https://drive.google.com/drive/folders/'+encodeURIComponent(session.folderId);const participants=service.transport.lastParticipants||[];const pending=participants.some(p=>p.writer==='unclaimed');$('connectionStatus').textContent=session?(pending?'Waiting for your partner to join. Share the household folder above.':participants.length>1?'Household device files are linked. Changes sync while each app is open.':'This device is connected. Partner connection has not been verified yet.'):'Create a new household, or join the one shared with you.';
  $('pickFolder').disabled=!!session;const retained=selectedFolder&&getBinding(selectedFolder.id);$('createJournal').textContent=!session&&retained?'Reconnect this device’s sync file':'Add this device';$('disconnect').disabled=!session;
  const binding=session&&getBinding(session.workspaceId);
  $('sync').disabled=!service.token||!session||!binding;$('createJournal').disabled=!!binding;$('pickPeers').disabled=!service.token||!session;
  $('ownFile').replaceChildren();if(binding){const link=document.createElement('a');link.href='https://drive.google.com/file/d/'+encodeURIComponent(binding.fileId)+'/view';link.target='_blank';link.rel='noopener';link.textContent='Open this device’s sync file in Drive';$('ownFile').append(link)}
  $('peerFiles').replaceChildren();for(const file of session?.files||[]){const item=document.createElement('li');item.textContent=(file.name||'Household device')+(file.id===binding?.fileId?' (this device)':'');if(file.id!==binding?.fileId){const remove=document.createElement('button');remove.textContent='Stop reading this device';remove.onclick=()=>run(async()=>{if(!confirm('Stop reading this device’s changes? Previously received tasks stay local. This does not change anyone’s Google Drive permissions.'))return;service.stop();const current=await local('GET');await service.commit(current,current.records,{...current.metadata,session:{...current.metadata.session,files:current.metadata.session.files.filter(f=>f.id!==file.id)}});if(service.token)await service.start(service.token);});item.append(remove);}$('peerFiles').append(item)}
  status(service.status+(s.metadata.lastSync?'\nLast sync: '+new Date(s.metadata.lastSync).toLocaleString():''));
  $('conflicts').replaceChildren();for(const conflict of s.metadata.conflicts||[]){
    const box=document.createElement('div');box.className='conflict';const title=document.createElement('p');title.textContent=(s.records[conflict.key]?.title||conflict.key)+' · '+(conflict.field==='$exists'?'Delete or keep':conflict.field);box.append(title);
    for(const c of new Map(conflict.choices.map(c=>[JSON.stringify(c.value),c])).values()){
      const button=document.createElement('button');button.textContent=conflict.field==='$exists'?(c.value?'Keep task':'Delete task'):typeof c.value==='string'?c.value:JSON.stringify(c.value);button.onclick=()=>run(()=>service.choose(conflict.key,conflict.field,c.value));box.append(button);
    }$('conflicts').append(box);
  }
}
service.changed=()=>show().catch(error=>status(error.message));
async function run(fn){if(busy)return;busy=true;try{await fn();await show()}catch(error){await show().catch(()=>{});status(error.message)}finally{busy=false}}
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
  await new Promise((resolve,reject)=>{const auth=google.accounts.oauth2.initTokenClient({client_id:clientId,scope:SCOPE,callback:result=>{if(generation!==uiGeneration)return reject(Error('Google connection was paused.'));if(result.error)return reject(Error(result.error));if(!google.accounts.oauth2.hasGrantedAllScopes(result,SCOPE))return reject(Error('The selected-file Drive permission was not granted.'));const grantedToken=result.access_token;service.token=grantedToken;setTimeout(()=>{if(service.token===grantedToken){uiGeneration++;host.tetherHomeSetup?.stop();service.token='';service.stop();service.status='Reconnect Google Drive; your edits are safe.';service.changed(service)}},Math.max(0,(Number(result.expires_in)-30)*1000));resolve()},error_callback:()=>reject(Error('Google sign-in was cancelled or blocked.'))});auth.requestAccessToken({prompt:''})});
  const s=await local('GET');service.status='Google connected';if(s.metadata.session&&getBinding(s.metadata.session.workspaceId)){service.transport.binding=getBinding(s.metadata.session.workspaceId);await service.start(service.token)}
});
function chooseFiles(folder=false,parent=null){
  if(!service.token)throw Error('Connect Google Drive first.');
  return new Promise((resolve,reject)=>{
    const view=new google.picker.DocsView(google.picker.ViewId.DOCS).setMode(google.picker.DocsViewMode.LIST);
    if(parent)view.setParent(parent);if(folder)view.setIncludeFolders(true).setSelectFolderEnabled(true).setMimeTypes('application/vnd.google-apps.folder');else view.setMimeTypes('application/json');
    const builder=new google.picker.PickerBuilder().addView(view).setOAuthToken(service.token).setDeveloperKey($('pickerKey').value.trim()).setAppId($('projectNumber').value.trim()).setOrigin(location.origin).setCallback(data=>{
      if(data.action===google.picker.Action.PICKED){picker?.dispose();picker=null;resolve(data.docs||[])}else if(data.action===google.picker.Action.CANCEL){picker?.dispose();picker=null;resolve([])}
    });if(!folder)builder.enableFeature(google.picker.Feature.MULTISELECT_ENABLED);picker=builder.build();picker.setVisible(true);
  });
}
function requireSetup(){if(!service.token)throw Error('Connect your Google account first.');if(!$('consent').checked)throw Error('Confirm which Home data you want to share.');}
const deviceName=()=>($('deviceName').value.trim()||'My device').slice(0,60);
async function activateHousehold(folder,files,binding,control={isActive:()=>true}){
  const check=()=>{if(!control.isActive())throw Error('Setup paused. Resume when ready.');};check();
  localStorage.setItem(storagePrefix+'writer:'+folder.id,JSON.stringify(binding));service.transport.binding=binding;selectedFolder=folder;
  const session={mode:'selected-journals',folderId:folder.id,folderName:folder.name,workspaceId:folder.id,files};
  const current=await local('GET');check();
  if(current.metadata.session){if(current.metadata.session.workspaceId!==folder.id)throw Error('Disconnect the existing household before resuming this setup.');const combined=[...new Map([...current.metadata.session.files,...files].map(f=>[f.id,f])).values()];await service.commit(current,current.records,{...current.metadata,session:{...current.metadata.session,files:combined}});check();}
  else{await service.configure(session,{publishExisting:true});check();}
  await service.start(service.token);check();
}
$('resumeSetup').onclick=()=>run(async()=>{requireSetup();await setup.resume(service.token)});
$('abandonSetup').onclick=()=>run(async()=>{if(confirm('Forget pending setup? Files already created in Drive are kept. Check Drive before creating another household.'))setup.abandon()});
$('createHousehold').onclick=()=>run(async()=>{
  requireSetup();const name=$('householdName').value.trim();if(!name)throw Error('Give your household a name.');const current=await local('GET');if(current.metadata.session)throw Error('Disconnect the existing household first.');
  service.stop();await setup.create(service.token,{name,deviceName:deviceName()});
});
$('joinHousehold').onclick=()=>run(async()=>{
  requireSetup();const generation=uiGeneration,check=()=>{if(generation!==uiGeneration)throw Error('Setup paused.');};const current=await local('GET');check();if(current.metadata.session)throw Error('Disconnect the existing household first.');const folders=await chooseFiles(true);check();if(!folders.length)return;
  const folder=await service.transport.folder(service.token,folders[0].id);check();selectedFolder=folder;status('Select both Tether household files in this folder.');const picked=await chooseFiles(false,folder.id);check();if(!picked.length)return;
  const inspected=[];for(const file of picked){const data=await service.transport.readJournal(service.token,file.id,folder.id);check();inspected.push({file,journal:data.journal})}
  if(inspected.length<2)throw Error('Select both household files so both people can see updates.');
  const retained=getBinding(folder.id);
  if(retained&&inspected.some(p=>p.file.id===retained.fileId&&p.journal.writer===device)){await activateHousehold(folder,inspected.map(p=>({id:p.file.id,name:p.file.name||'Household device'})),retained,{isActive:()=>generation===uiGeneration});return;}
  const slots=inspected.filter(p=>p.journal.writer==='unclaimed'&&!p.journal.operations.length);if(slots.length!==1)throw Error('No single open partner slot was selected. Select the two household files, or use Another device to add an extra device.');
  service.stop();await setup.join(service.token,{folder,files:inspected.map(p=>({id:p.file.id,name:p.file.name||'Household device'})),slotId:slots[0].file.id});
});
$('copyInvite').onclick=()=>run(async()=>{const s=await local('GET');if(!s.metadata.session)throw Error('Create or join a household first.');await navigator.clipboard.writeText('https://drive.google.com/drive/folders/'+s.metadata.session.folderId);service.status='Household link copied. Share access in Google Drive before sending it.';});
$('pickFolder').onclick=()=>run(async()=>{const files=await chooseFiles(true);if(files[0])selectedFolder=await service.transport.folder(service.token,files[0].id)});
$('createJournal').onclick=()=>run(async()=>{
  requireSetup();if(!selectedFolder)throw Error('Choose the shared folder first.');const generation=uiGeneration,check=()=>{if(generation!==uiGeneration)throw Error('Setup paused.');};
  const s=await local('GET');check();if(s.metadata.session&&s.metadata.session.folderId!==selectedFolder.id)throw Error('Disconnect the existing shared Home before changing folders.');
  const workspace=selectedFolder.id,retained=getBinding(workspace);if(s.metadata.session&&retained)throw Error('This browser already has a sync file.');service.stop();
  if(retained){const previous=await service.transport.readJournal(service.token,retained.fileId,workspace);check();if(previous.journal.writer!==device)throw Error('The saved device file belongs to another writer.');await activateHousehold(selectedFolder,[{id:retained.fileId,name:'This device'}],retained,{isActive:()=>generation===uiGeneration});}
  else await setup.add(service.token,{folder:selectedFolder,deviceName:deviceName()});
});
$('pickPeers').onclick=()=>run(async()=>{
  const current=await local('GET');const files=await chooseFiles(false,current.metadata.session?.folderId);if(!files.length)return;service.stop();let s=await local('GET');if(!s.metadata.session)throw Error('Create this device’s sync file first.');
  const additions=[];for(const file of files){await service.transport.readJournal(service.token,file.id,s.metadata.session.workspaceId);additions.push({id:file.id,name:file.name||file.id})}
  s=await local('GET');const combined=[...new Map([...(s.metadata.session.files||[]),...additions].map(f=>[f.id,f])).values()];await service.commit(s,s.records,{...s.metadata,session:{...s.metadata.session,files:combined}});await service.start(service.token);
});
$('sync').onclick=()=>run(()=>service.sync());$('pause').onclick=()=>{uiGeneration++;setup.stop();service.stop();service.status='Paused; local edits are safe';show()};
$('disconnect').onclick=()=>run(async()=>{if(confirm('Stop syncing this Home workspace? Local tasks and Drive files will be kept.')){uiGeneration++;setup.stop();await service.disconnect();selectedFolder=null}});
$('externalBrowser').onclick=()=>run(async()=>{const response=await fetcher('/api/drive-sync/open-browser',{method:'POST',headers:{'X-Tether-Workspace':'home'}});if(!response.ok)throw Error('Could not open the system browser');status('Continue in your normal browser.')});
if(!browser&&!new URLSearchParams(location.search).has('external')){$('desktopNotice').hidden=false;$('connect').disabled=true}
window.addEventListener('pagehide',()=>{uiGeneration++;setup.stop();picker?.dispose();if(!browser)service.stop()});
await show().catch(error=>status(error.message));
