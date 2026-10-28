/* Shared screens delegate requests to the persistent, same-origin app shell. */
(() => {
  const config=window.TETHER_CONFIG;
  let shell;
  try{shell=window.top.location.origin===location.origin && window.top.tetherReady ? window.top : null}catch(_){}
  if(!shell){
    const query=new URLSearchParams(location.search),page=location.pathname.split('/').at(-1);
    if(page==='board.html')query.set('view','board');if(page==='snapshots.html')query.set('view','snapshots');
    location.replace(config.base+(query.size?'?'+query:'')+location.hash);return;
  }
  window.fetch=(...args)=>shell.tetherReady.then(runtime=>runtime.fetch(...args));
  const api=async(path,method='GET',data)=>{
    const response=await fetch(config.base+'api'+path,{method,headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
    const result=await response.json();if(!response.ok){const error=Error(result.detail||'Request failed');error.status=response.status;throw error}window.tetherDataChanged?.(path,method);return result;
  };
  const $=selector=>document.querySelector(selector);
  function status(selector,text){const node=$(selector);if(node)node.textContent=text}
  function configuration(c){
    $('#base').value=c.base_url;$('#model').value=c.model;$('#key').value='';$('#rememberKey').checked=c.remember;
    $('#unlockKey').hidden=!c.has_saved_key;$('#lockKey').hidden=!c.has_key;
    status('#keyStatus',c.locked?'Saved key is locked. Enter its passphrase and unlock it.':c.has_key?
      (c.remember?'Key is unlocked. It is saved encrypted for your next visit.':'Key is ready for this session. To keep it after closing the app, save it encrypted with a passphrase.'):
      'Enter your API key, then save or test the connection.');
    window.tetherProviderConfigured?.(c);
  }
  let loadingSettings=Promise.resolve(),pendingProvider=Promise.resolve();
  window.tetherPrepareUpdate=async()=>{
    await pendingProvider;
    if(document.querySelector('#voiceInput[aria-pressed="true"]'))return false;
    // Keep unsaved forms and task/meeting-note editors open until the user closes them.
    if([...document.querySelectorAll('#settings,#chatSelection,#actionDrawer,.panel')].some(el=>el.getClientRects().length))return false;
    const input=$('#message');if(input)try{localStorage.setItem('tether-chat-draft',input.value)}catch(_){return false}
    return true;
  };
  window.tetherLoadSettings=()=>loadingSettings=(async()=>{
    await pendingProvider;
    const form=$('#provider'),controls=[...form.querySelectorAll('input,select,button')];
    form.setAttribute('aria-busy','true');for(const control of controls)control.disabled=true;
    try{configuration(await api('/settings'));await window.tetherLoadPreferences?.()}catch(e){status('#providerStatus',e.message)}
    finally{for(const control of controls)control.disabled=false;form.removeAttribute('aria-busy')}
  })();
  window.tetherBeforeChat=async(text,attention)=>{
    try{await pendingProvider;await api('/chat/preflight','POST',{text,attention});return true}
    catch(error){
      if(error.status!==401)return true;
      if($('#settings').classList.contains('hidden'))$('#navsettings').click();
      await loadingSettings;
      status('#providerStatus','Your message is still in the draft. '+error.message);
      const target=$('#unlockKey').hidden?$('#key'):$('#keyPassphrase');target.focus();target.scrollIntoView({block:'center'});
      return false;
    }
  };
  window.tetherLoadStorage=async()=>{
    const persistent=await navigator.storage?.persisted?.().catch(()=>false);
    status('#storageStatus',persistent?'Local storage protection is enabled. Keep an exported backup too.':'Use Protect local storage to request storage protection, and keep an exported backup.');
  };
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.target==='_blank')return;
    const url=new URL(link.href,location.href);
    if(url.origin===location.origin && ['conversation.html','board.html','snapshots.html'].some(page=>url.pathname===config.base+page)){
      // The screen's own task-drawer handlers run before this bubbling listener.
      event.preventDefault();shell.tetherNavigate(url.href);
    }
  });
  window.addEventListener('hashchange',()=>{if(window.parent===shell)shell.tetherSyncRoute(location.href)});
  window.tetherDownload=async(blob,filename)=>{
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);
  };
  document.addEventListener('DOMContentLoaded',()=>{
    if(!$('#provider'))return;
    status('#browserVersion','tether. '+config.version+' · Browser edition');
    const form=$('#provider');let providerBusy=false;
    function providerAction(action,validate=false){
      if(providerBusy)return pendingProvider;
      providerBusy=true;
      return pendingProvider=(async()=>{
        await loadingSettings;
        const controls=[...form.querySelectorAll('input,select,button')];
        try{
          if(validate){await window.tetherRequireModel?.();if(!form.reportValidity())return}
          form.setAttribute('aria-busy','true');for(const control of controls)control.disabled=true;
          await action();
        }catch(e){status('#providerStatus',e.message)}
        finally{providerBusy=false;for(const control of controls)control.disabled=false;form.removeAttribute('aria-busy')}
      })();
    }
    async function saveConnection(){
      const c=await api('/settings','POST',{base_url:$('#base').value.trim(),model:$('#model').value.trim(),api_key:$('#key').value.trim()||null,
        remember:$('#rememberKey').checked,passphrase:$('#keyPassphrase').value});
      configuration(c);$('#keyPassphrase').value='';
      status('#providerStatus',c.locked?'Connection saved. Unlock your saved key to connect.':c.remember?'Connection saved on this device and ready to chat.':'Connection saved for this session and ready to chat.');
      return c;
    }
    form.onsubmit=event=>{event.preventDefault();providerAction(saveConnection,true)};
    $('#unlockKey').onclick=()=>providerAction(async()=>{configuration(await api('/settings/unlock','POST',{passphrase:$('#keyPassphrase').value}));$('#keyPassphrase').value='';status('#providerStatus','Saved key unlocked.')});
    $('#lockKey').onclick=()=>providerAction(async()=>{await api('/settings/lock','POST',{});$('#key').value='';$('#keyPassphrase').value='';configuration(await api('/settings'));status('#providerStatus','Key locked.')});
    $('#forgetKey').onclick=()=>providerAction(async()=>{const c=await api('/settings');configuration(await api('/settings','POST',{...c,remember:false,clear_key:true}));$('#keyPassphrase').value='';status('#providerStatus','Saved key removed.')});
    $('#testConnection').onclick=()=>providerAction(async()=>{
      await window.tetherDiscoverModels?.();
      await saveConnection();status('#providerStatus','Testing provider…');
      const result=await api('/settings/test','POST',{});status('#providerStatus',result.message);
    },true);
    $('#exportData').onclick=async()=>{try{const backup=await api('/backup');await window.tetherDownload(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'}),'tether-backup-'+new Date().toISOString().slice(0,10)+'.json');status('#storageStatus','Backup prepared. Save the downloaded file.')}catch(e){status('#storageStatus',e.message)}};
    $('#importData').onchange=async event=>{const file=event.target.files[0];if(!file)return;
      try{if(file.size>20*1024*1024)throw Error('Choose a JSON backup smaller than 20 MB.');const result=await api('/import','POST',JSON.parse(await file.text()));
        status('#storageStatus','Imported '+result.added.tasks+' tasks and '+result.added.messages+' messages. Existing records were retained.');
        if($('#board')){load()}else window.dispatchEvent(new Event('pageshow'));
      }catch(e){status('#storageStatus','Import did not finish: '+e.message)}finally{event.target.value=''}
    };
    $('#persistData').onclick=async()=>{try{const granted=await navigator.storage?.persist?.();status('#storageStatus',granted?'Local storage protection enabled. Keep an exported backup too.':'This browser manages storage automatically. Keep an exported backup.')}catch(e){status('#storageStatus',e.message)}};
    $('#installApp').onclick=async()=>{if(!await shell.tetherInstall())status('#storageStatus','On iPhone, use Safari → Share → Add to Home Screen. On other browsers, use the Install app command in the browser menu.')};
    $('#enableNotifications').onclick=async()=>{
      if(!('Notification' in shell)){status('#notificationStatus','This browser does not support notifications here. Due items still appear in Attention.');return}
      try{const permission=await shell.Notification.requestPermission();status('#notificationStatus',permission==='granted'?'Notifications enabled while tether is open.':'Notifications were not enabled.');if(permission==='granted')await shell.tetherNotify()}catch(e){status('#notificationStatus','Notifications are unavailable here. On iPhone, add tether to your Home Screen first.')}
    };
    if($('#chat')){
      const button=document.createElement('button');button.id='mobileAttention';button.type='button';button.className='settings-gear';button.title='Attention';button.setAttribute('aria-label','Attention');
      button.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>';
      button.onclick=()=>{const open=document.body.classList.toggle('browser-attention-open');button.setAttribute('aria-expanded',String(open))};$('#navsettings').before(button);
      $('#due').addEventListener('click',event=>{if(event.target.closest('button'))document.body.classList.remove('browser-attention-open')});
    }
  });
})();
