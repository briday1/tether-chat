/* A persistent, local-data dashboard. Refreshing never calls the AI provider. */
(() => {
  const $=selector=>document.querySelector(selector),frame=$('#display-calendar');
  const mode=()=>window.tetherWorkspace || new URLSearchParams(location.search).get('workspace') || 'work';
  const storageKey=()=>`tether-display:${location.pathname}:${mode()}`;
  const iso=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const validDate=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(value+'T12:00:00').valueOf());
  let view='month',anchor=iso(new Date()),followingToday=true,weekStart=1,density='compact',revision=0,lastRange='',busy=false;
  try{const saved=JSON.parse(localStorage.getItem(storageKey())||'{}');if(['compact','comfortable'].includes(saved.density))density=saved.density;if(saved.followingToday===false && validDate(saved.anchor)){anchor=saved.anchor;followingToday=false}}catch(_){}
  function persist(){try{localStorage.setItem(storageKey(),JSON.stringify({view,anchor,followingToday,density}))}catch(_){}}
  function sidebar(open){$('.display-main').inert=open;$('#display-sidebar').hidden=!open;$('#display-backdrop').hidden=!open;$('#display-menu').setAttribute('aria-expanded',String(open));if(open)$('#display-close').focus();else $('#display-menu').focus()}
  $('#display-menu').onclick=()=>sidebar($('#display-sidebar').hidden);
  $('#display-close').onclick=$('#display-backdrop').onclick=()=>sidebar(false);
  document.addEventListener('keydown',event=>{
    if($('#display-sidebar').hidden)return;
    if(event.key==='Escape'){event.preventDefault();sidebar(false)}
    if(event.key==='Tab'){const focusable=[...$('#display-sidebar').querySelectorAll('button,a,input,select')].filter(el=>!el.disabled);const first=focusable[0],last=focusable.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}
  });
  function clock(){const now=new Date();$('#display-clock').dateTime=now.toISOString();$('#display-clock').textContent=now.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'})+' - '+now.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',hour12:true}).replace(/\s/g,'')}
  async function syncStatus(){
    const label=$('#display-sync');
    try{
      if(!navigator.onLine){label.textContent='Offline · showing saved items';label.dataset.warning='true';return}
      const host=window.parent!==window?window.parent:window,service=host.tetherHomeSync;
      if(!service){label.textContent='Local calendar';label.dataset.warning='false';return}
      const state=await service.state();
      if(!state.metadata.session){label.textContent='Local calendar';label.dataset.warning='false';return}
      const last=Date.parse(state.metadata.lastSync||''),age=Date.now()-last;
      if(!service.token){label.textContent='Reconnect Google in Settings';label.dataset.warning='true'}
      else if(!service.timer){label.textContent='Household sync paused';label.dataset.warning='true'}
      else if(state.metadata.conflicts?.length){label.textContent='Sync needs a choice in Settings';label.dataset.warning='true'}
      else if(service.status!=='Synced'&&service.status!=='Google connected'){label.textContent=service.status||'Waiting for household sync';label.dataset.warning='true'}
      else if(!Number.isFinite(last)||age>180000){label.textContent='Household updates delayed · check Settings';label.dataset.warning='true'}
      else{label.textContent='Household synced '+new Date(last).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});label.dataset.warning='false'}
    }catch(_){label.textContent='Could not check household sync';label.dataset.warning='true'}
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
  function renderQuick(data){
    const days=data.days||[],today=iso(new Date()),items=days.flatMap(day=>(day.tasks||[]).map(task=>({...task,date:day.date}))).filter(task=>task.state!=='settled');
    const container=$('#display-quick');container.replaceChildren();
    const summary=document.createElement('span');summary.textContent=`${items.length} scheduled ${items.length===1?'item':'items'} · ${items.filter(task=>task.date===today).length} today`;container.append(summary);
    const next=items.find(task=>task.date>=today);
    if(next){const link=document.createElement('a');link.href='/board#'+(next.action_id?'action/'+encodeURIComponent(next.task_id||next.id)+'/'+encodeURIComponent(next.action_id):'task/'+encodeURIComponent(next.task_id||next.id));link.textContent='Next: '+next.title;link.title=next.date;container.append(link)}
    if(!items.length){const note=document.createElement('span');note.textContent='Add a reminder or due date in Tasks to place an item here.';container.append(note)}
  }
  async function refresh(force=false){
    if(busy && !force)return;
    busy=true;const request=++revision;
    try{
      if(followingToday)anchor=iso(new Date());
      persist(); // Save the user's view before any asynchronous refresh/navigation.
      const {start,end}=range(),key=`${start}:${end}:${density}`;
      const date=new Date(anchor+'T12:00:00');$('#display-title').textContent=view==='month'?date.toLocaleDateString(undefined,{month:'long',year:'numeric'}):new Date(start+'T12:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric'})+' – '+new Date(end+'T12:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
      $('#display-density').value=density;clock();syncStatus();
      $('#display-date').value=anchor;
      if(key!==lastRange){lastRange=key;frame.contentWindow.location.replace('/snapshots?'+new URLSearchParams({start,end,embed:'1',layout:'display',density,workspace:mode()}));}
      else frame.contentWindow?.postMessage({type:'tether:snapshot-refresh'},location.origin);
      const response=await fetch('/api/snapshot?'+new URLSearchParams({start,end}));
      if(!response.ok)throw Error('Could not refresh this calendar. Your saved tasks have not changed.');
      const data=await response.json();if(request!==revision)return;
      renderQuick(data);$('#display-error').textContent='';$('#display-error').hidden=true;$('#display-status').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})+' · refreshes automatically';persist();
    }catch(error){if(request===revision){$('#display-error').textContent=error.message;$('#display-error').hidden=false}}
    finally{if(request===revision)busy=false}
  }
  function step(direction){const date=new Date(anchor+'T12:00:00');if(view==='month'){date.setDate(1);date.setMonth(date.getMonth()+direction)}else date.setDate(date.getDate()+7*direction);anchor=iso(date);followingToday=false;refresh(true)}
  $('#previous').onclick=$('#display-previous').onclick=()=>step(-1);$('#next').onclick=$('#display-next').onclick=()=>step(1);
  $('#today').onclick=$('#display-today').onclick=()=>{followingToday=true;refresh(true);frame.contentWindow?.postMessage({type:'tether:snapshot-today'},location.origin)};
  $('#display-date').onchange=event=>{if(validDate(event.target.value)){anchor=event.target.value;followingToday=false;refresh(true)}};
  $('#display-density').onchange=event=>{density=event.target.value;refresh(true)};
  frame.addEventListener('load',theme);
  new MutationObserver(theme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','style']});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
    // Dashboard owns iframe height; snapshot content fits that viewport.
    if(event.data?.type==='tether:snapshot-task' && /^[A-Za-z0-9_-]+$/.test(event.data.id||'')){
      const action=event.data.action_id;if(action && !/^[A-Za-z0-9_-]+$/.test(action))return;
      const href='/board#'+(action?'action/'+event.data.id+'/'+action:'task/'+event.data.id);location.href=window.tetherWorkspaceURL?window.tetherWorkspaceURL(href):href;
    }
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
  window.addEventListener('focus',()=>refresh());
  const statusTimer=setInterval(()=>{clock();if(!document.hidden)syncStatus()},15000);
  const timer=setInterval(()=>{if(!document.hidden)refresh()},60000);
  window.addEventListener('pagehide',()=>{clearInterval(timer);clearInterval(statusTimer)},{once:true});
  fetch('/api/preferences').then(response=>response.ok?response.json():{}).then(preferences=>{weekStart=preferences.week_start??1;refresh(true)}).catch(()=>refresh(true));
})();
