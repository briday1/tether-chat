/* A persistent, local-data dashboard. Refreshing never calls the AI provider. */
(() => {
  const $=selector=>document.querySelector(selector),frame=$('#display-calendar');
  const mode=()=>window.tetherWorkspace || new URLSearchParams(location.search).get('workspace') || 'work';
  const storageKey=()=>`tether-display:${location.pathname}:${mode()}`;
  const iso=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  let view='month',anchor=iso(new Date()),followingToday=true,weekStart=1,density='compact',revision=0,lastRange='',busy=false,detailOpen=false;
  try{const saved=JSON.parse(localStorage.getItem(storageKey())||'{}');if(['compact','comfortable'].includes(saved.density))density=saved.density}catch(_){}
  function persist(){try{localStorage.setItem(storageKey(),JSON.stringify({density}))}catch(_){}}
  function sidebar(open){$('.display-main').inert=open;$('.display-bar').inert=open;const chat=$('#display-quick-chat');if(chat)chat.inert=open;$('#display-sidebar').hidden=!open;$('#display-backdrop').hidden=!open;$('#display-menu').setAttribute('aria-expanded',String(open));if(open)$('#display-close').focus();else $('#display-menu').focus()}
  $('#display-menu').onclick=()=>sidebar($('#display-sidebar').hidden);
  $('#display-close').onclick=$('#display-backdrop').onclick=()=>sidebar(false);
  document.addEventListener('keydown',event=>{
    if($('#display-sidebar').hidden)return;
    if(event.key==='Escape'){event.preventDefault();sidebar(false)}
    if(event.key==='Tab'){const focusable=[...$('#display-sidebar').querySelectorAll('button,a,input,select')].filter(el=>!el.disabled);const first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}
  });
  const settingsDialog=$('#display-settings-dialog'),settingsFrame=$('#display-settings-frame');
  function dismissSettings(){settingsDialog.close();settingsFrame.contentWindow.location.replace('about:blank');$('#display-settings').focus();syncStatus()}
  function closeSettings(){if(!settingsDialog.open)return;dismissSettings();if(history.state?.tetherDisplayOverlay==='settings'){$('#display-settings').disabled=true;history.back()}}
  function openSettings(){if(settingsDialog.open)return;settingsFrame.contentWindow.location.replace('/?settings=display');settingsDialog.showModal()}
  window.addEventListener('popstate',()=>{const closing=$('#display-settings').disabled;$('#display-settings').disabled=false;if(history.state?.tetherDisplayOverlay==='settings')openSettings();else if(settingsDialog.open)dismissSettings();else if(closing)$('#display-settings').focus()});
  $('#display-settings').onclick=()=>{openSettings();history.pushState({...history.state,tetherDisplayOverlay:'settings'},'',location.href)};
  settingsDialog.addEventListener('cancel',event=>{event.preventDefault();closeSettings()});
  settingsDialog.addEventListener('click',event=>{if(event.target===settingsDialog){const box=settingsDialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeSettings()}});
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===settingsFrame.contentWindow&&event.data?.type==='tether:settings-close')closeSettings();if(event.origin===location.origin&&event.source===settingsFrame.contentWindow&&event.data?.type==='tether:settings-theme'&&typeof event.data.theme==='string')document.documentElement.dataset.theme=event.data.theme});
  function clock(){const now=new Date();$('#display-clock').dateTime=now.toISOString();$('#display-clock-date').textContent=now.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'});$('#display-clock-time').textContent=now.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',hour12:true}).replace(/\s+/g,' ')}
  async function syncStatus(){
    const label=$('#display-sync'),gear=$('#display-settings');
    label.hidden=true;gear.removeAttribute('data-warning');gear.title='Settings';
    const warning=text=>{label.textContent=text;label.hidden=false;gear.dataset.warning='true';gear.title=text;};
    try{
      if(!navigator.onLine){warning('Offline · showing saved items');return}
      const host=window.parent!==window?window.parent:window,service=host.tetherHomeSync;
      if(!service){return}
      const state=await service.state();
      if(!state.metadata.session){return}
      const last=Date.parse(state.metadata.lastSync||''),age=Date.now()-last;
      if(!service.token){warning('Reconnect Google in Settings')}
      else if(!service.timer){warning('Household sync paused')}
      else if(state.metadata.conflicts?.length){warning('Sync needs a choice in Settings')}
      else if(service.status!=='Synced'&&service.status!=='Google connected'){warning(service.status||'Waiting for household sync')}
      else if(!Number.isFinite(last)||age>180000){warning('Household updates delayed · check Settings')}
      else{gear.title='Settings'}
    }catch(_){warning('Could not check household sync')}
  }
  function range(){
    const first=new Date(anchor+'T12:00:00'),last=new Date(first);
    if(view==='month'){first.setDate(1);last.setMonth(last.getMonth()+1,0)}
    else{first.setDate(first.getDate()-(first.getDay()-weekStart+7)%7);last.setTime(first.getTime());last.setDate(last.getDate()+6)}
    return {start:iso(first),end:iso(last)};
  }
  function theme(){
    const style=getComputedStyle(document.documentElement),variables={};
    for(const name of ['page','paper','panel','text','muted','line','soft','accent','accent-text','highlight'])variables[name]=style.getPropertyValue('--'+name).trim();
    frame.contentWindow?.postMessage({type:'tether:snapshot-theme',theme:document.documentElement.dataset.theme,variables},location.origin);
  }
  async function refresh(force=false){
    if(detailOpen || (busy && !force))return;
    busy=true;const request=++revision;
    try{
      if(followingToday)anchor=iso(new Date());
      persist(); // Save the user's view before any asynchronous refresh/navigation.
      const {start,end}=range(),key=`${start}:${end}:${density}`;
      const date=new Date(anchor+'T12:00:00');$('#display-title').textContent=view==='month'?date.toLocaleDateString(undefined,{month:'long',year:'numeric'}):new Date(start+'T12:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric'})+' – '+new Date(end+'T12:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
      clock();syncStatus();
      if(key!==lastRange){lastRange=key;frame.contentWindow.location.replace('/snapshots?'+new URLSearchParams({start,end,embed:'1',layout:'display',density,workspace:mode()}));}
      else frame.contentWindow?.postMessage({type:'tether:snapshot-refresh'},location.origin);
      const response=await fetch('/api/snapshot?'+new URLSearchParams({start,end}));
      if(!response.ok)throw Error('Could not refresh this calendar. Your saved tasks have not changed.');
      const data=await response.json();if(request!==revision)return;
      $('#display-error').textContent='';$('#display-error').hidden=true;$('#display-status').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})+' · refreshes automatically';persist();
    }catch(error){if(request===revision){$('#display-error').textContent=error.message;$('#display-error').hidden=false}}
    finally{if(request===revision)busy=false}
  }
  function step(direction){const date=new Date(anchor+'T12:00:00');if(view==='month'){date.setDate(1);date.setMonth(date.getMonth()+direction)}else date.setDate(date.getDate()+7*direction);anchor=iso(date);followingToday=false;refresh(true)}
  $('#display-previous').onclick=()=>step(-1);$('#display-next').onclick=()=>step(1);
  $('#display-today').onclick=()=>{followingToday=true;refresh(true);frame.contentWindow?.postMessage({type:'tether:snapshot-today'},location.origin)};
  frame.addEventListener('load',()=>{detailOpen=false;$('.display-bar').inert=false;const chat=$('#display-quick-chat');if(chat){chat.inert=false;chat.style.visibility=''}theme()});
  new MutationObserver(theme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','style']});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
    // Task details are modal across the dock, not just inside the calendar iframe.
    if(event.data?.type==='tether:snapshot-detail'){
      detailOpen=event.data.open===true;
      $('.display-bar').inert=detailOpen;
      const chat=$('#display-quick-chat');if(chat){chat.inert=detailOpen;chat.style.visibility=detailOpen?'hidden':''}
      if(!detailOpen)refresh();
      return;
    }
    // Dashboard owns iframe height; snapshot content fits that viewport.
    if(event.data?.type==='tether:snapshot-task' && /^[A-Za-z0-9_-]+$/.test(event.data.id||'')){
      const action=event.data.action_id;if(action && !/^[A-Za-z0-9_-]+$/.test(action))return;
      const href='/board#'+(action?'action/'+event.data.id+'/'+action:'task/'+event.data.id);location.href=window.tetherWorkspaceURL?window.tetherWorkspaceURL(href):href;
    }
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
  window.addEventListener('focus',()=>refresh());
  window.addEventListener('tether:data-changed',()=>refresh(true));
  // A local midnight must advance Today even if the preceding data request is slow.
  const statusTimer=setInterval(()=>{clock();if(!document.hidden){if(followingToday&&anchor!==iso(new Date()))refresh(true);syncStatus()}},15000);
  const timer=setInterval(()=>{if(!document.hidden)refresh()},60000);
  window.addEventListener('pagehide',event=>{if(!event.persisted){clearInterval(timer);clearInterval(statusTimer)}});
  window.addEventListener('pageshow',event=>{if(event.persisted){followingToday=true;refresh(true);frame.contentWindow?.postMessage({type:'tether:snapshot-today'},location.origin)}});
  refresh(true); // First frame follows device-local Today, without waiting for preferences.
  fetch('/api/preferences').then(response=>response.ok?response.json():{}).then(preferences=>{weekStart=preferences.week_start??1;refresh(true)}).catch(()=>refresh(true));
})();
