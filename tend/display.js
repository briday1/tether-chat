/* A persistent, local-data dashboard. Refreshing never calls the AI provider. */
(() => {
  const $=selector=>document.querySelector(selector),frame=$('#display-calendar');
  const mode=()=>window.tetherWorkspace || new URLSearchParams(location.search).get('workspace') || 'work';
  const storageKey=()=>`tether-display:${location.pathname}:${mode()}`;
  const iso=date=>`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  const validDate=value=>typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(value+'T12:00:00').valueOf());
  let view='week',anchor=iso(new Date()),followingToday=true,weekStart=1,revision=0,lastRange='',busy=false;
  try{const saved=JSON.parse(localStorage.getItem(storageKey())||'{}');if(saved.view==='month')view='month';if(saved.followingToday===false && validDate(saved.anchor)){anchor=saved.anchor;followingToday=false}}catch(_){}
  function persist(){try{localStorage.setItem(storageKey(),JSON.stringify({view,anchor,followingToday}))}catch(_){}}
  function range(){
    const first=new Date(anchor+'T12:00:00'),last=new Date(first);
    if(view==='month'){first.setDate(1);last.setMonth(last.getMonth()+1,0)}
    else{first.setDate(first.getDate()-(first.getDay()-weekStart+7)%7);last.setTime(first.getTime());last.setDate(last.getDate()+6)}
    return {start:iso(first),end:iso(last)};
  }
  function theme(){
    const style=getComputedStyle(document.documentElement),variables={};
    for(const name of ['page','paper','panel','text','muted','line','soft','accent','accent-text','highlight'])variables[name]=style.getPropertyValue('--'+name).trim();
    frame.contentWindow?.postMessage({type:'tend:snapshot-theme',theme:document.documentElement.dataset.theme,variables},location.origin);
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
      const {start,end}=range(),key=`${start}:${end}`;
      $('#display-date').value=anchor;
      $('#view-week').setAttribute('aria-pressed',String(view==='week'));$('#view-month').setAttribute('aria-pressed',String(view==='month'));
      if(key!==lastRange){lastRange=key;frame.src='/snapshots?'+new URLSearchParams({start,end,embed:'1',workspace:mode()});}
      else frame.contentWindow?.postMessage({type:'tend:snapshot-refresh'},location.origin);
      const response=await fetch('/api/snapshot?'+new URLSearchParams({start,end}));
      if(!response.ok)throw Error('Could not refresh this calendar. Your saved tasks have not changed.');
      const data=await response.json();if(request!==revision)return;
      renderQuick(data);$('#display-error').textContent='';$('#display-status').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})+' · refreshes automatically';persist();
    }catch(error){if(request===revision)$('#display-error').textContent=error.message}
    finally{if(request===revision)busy=false}
  }
  function step(direction){const date=new Date(anchor+'T12:00:00');if(view==='month'){date.setDate(1);date.setMonth(date.getMonth()+direction)}else date.setDate(date.getDate()+7*direction);anchor=iso(date);followingToday=false;refresh(true)}
  $('#previous').onclick=()=>step(-1);$('#next').onclick=()=>step(1);
  $('#today').onclick=()=>{followingToday=true;refresh(true)};
  for(const period of ['week','month'])$('#view-'+period).onclick=()=>{view=period;refresh(true)};
  $('#display-date').onchange=event=>{if(validDate(event.target.value)){anchor=event.target.value;followingToday=false;refresh(true)}};
  frame.addEventListener('load',theme);
  new MutationObserver(theme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','style']});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
    if(event.data?.type==='tend:snapshot-size' && Number.isFinite(event.data.height))frame.style.height=Math.max(190,Math.min(event.data.height+4,2500))+'px';
    if(event.data?.type==='tend:snapshot-task' && /^[A-Za-z0-9_-]+$/.test(event.data.id||'')){
      const action=event.data.action_id;if(action && !/^[A-Za-z0-9_-]+$/.test(action))return;
      const href='/board#'+(action?'action/'+event.data.id+'/'+action:'task/'+event.data.id);location.href=window.tetherWorkspaceURL?window.tetherWorkspaceURL(href):href;
    }
  });
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
  window.addEventListener('focus',()=>refresh());
  const timer=setInterval(()=>{if(!document.hidden)refresh()},60000);
  window.addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  fetch('/api/preferences').then(response=>response.ok?response.json():{}).then(preferences=>{weekStart=preferences.week_start??1;refresh(true)}).catch(()=>refresh(true));
})();
