import {createRuntime} from './runtime.mjs';
const config=window.TETHER_CONFIG,frame=document.querySelector('#app-frame'),loading=document.querySelector('#loading');
let current='',installPrompt=null;
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event});
window.tetherInstall=async()=>{if(!installPrompt)return false;await installPrompt.prompt();installPrompt=null;return true};
function pageURL(){
  const query=new URLSearchParams(location.search),view=query.get('view')||'conversation';query.delete('view');
  const page={board:'board.html',snapshots:'snapshots.html',conversation:'conversation.html'}[view]||'conversation.html';
  return config.base+page+(query.size?'?'+query:'')+location.hash;
}
function shellURL(url){
  const page=url.pathname.slice(config.base.length),query=new URLSearchParams(url.search);
  if(page==='board.html')query.set('view','board');else if(page==='snapshots.html')query.set('view','snapshots');else query.delete('view');
  return config.base+(query.size?'?'+query:'')+url.hash;
}
window.tetherNavigate=(href,{replace=false}={})=>{
  const url=new URL(href,location.origin);
  if(url.origin!==location.origin || !['conversation.html','board.html','snapshots.html'].some(page=>url.pathname===config.base+page))return;
  const next=url.pathname+url.search+url.hash;if(current===next)return;
  history[replace?'replaceState':'pushState']({},'',shellURL(url));current=next;frame.src=next;
};
window.tetherSyncRoute=href=>{
  const url=new URL(href,location.origin),next=url.pathname+url.search+url.hash;
  if(current!==next){current=next;history.replaceState({},'',shellURL(url))}
};
window.addEventListener('popstate',()=>{const next=pageURL();if(next!==current){current=next;frame.src=next}});
window.tetherReady=createRuntime({config});
try{
  const runtime=await window.tetherReady;window.tetherFetch=runtime.fetch;
  let checking=false,refreshing=false;
  async function checkRelease(){
    if(checking||refreshing||document.hidden||navigator.onLine===false)return;
    checking=true;
    try{
      const response=await fetch(config.base+'app-config.js?release='+Date.now(),{cache:'no-store'});
      if(!response.ok)return;
      const text=await response.text(),prefix='window.TETHER_CONFIG=';
      if(!text.startsWith(prefix))return;
      const latest=JSON.parse(text.slice(prefix.length).trim().replace(/;$/,''));
      const parts=v=>String(v).split('.').map(Number),[year,release]=parts(latest.version),[oldYear,oldRelease]=parts(config.version);
      if(!(year>oldYear||year===oldYear&&release>oldRelease))return;
      if(!await frame.contentWindow?.tetherPrepareUpdate?.())return;
      const state=await (await runtime.fetch(config.base+'api/chat/state')).json();
      if((state.jobs||[]).some(job=>['running','queued'].includes(job.status)))return;
      refreshing=true;
      location.replace(config.base+'update.html?automatic=1');
    }catch(_){ /* Keep the installed app working offline or during a failed deploy. */ }
    finally{checking=false}
  }
  window.addEventListener('online',checkRelease);
  window.addEventListener('focus',checkRelease);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkRelease()});
  navigator.serviceWorker?.addEventListener('controllerchange',checkRelease);
  navigator.serviceWorker?.addEventListener('message',event=>{if(event.data?.type==='TETHER_RELEASE_AVAILABLE')checkRelease()});
  setInterval(checkRelease,15000);
  frame.addEventListener('load',checkRelease);
  window.tetherNotify=()=>runtime.notifications();
  current=pageURL();frame.src=current;frame.hidden=false;loading.hidden=true;
  frame.addEventListener('load',()=>{
    try{
      const document=frame.contentDocument,root=document.documentElement;
      const theme=()=>{
        const background=getComputedStyle(root).getPropertyValue('--paper').trim()||'#f6f7f3';
        window.document.documentElement.style.background=background;
        window.document.querySelector('meta[name="theme-color"]').content=background;
      };theme();new MutationObserver(theme).observe(root,{attributes:true,attributeFilter:['data-theme','style']});
      window.tetherSyncRoute(frame.contentWindow.location.href);
    }catch(_){}
  });
  if('serviceWorker' in navigator)navigator.serviceWorker.register(config.base+'sw.js',{scope:config.base,updateViaCache:'none'})
    .then(registration=>{
      registration.addEventListener('updatefound',()=>registration.installing?.addEventListener('statechange',checkRelease));
      document.addEventListener('visibilitychange',()=>{if(!document.hidden)registration.update().catch(()=>{})});
      window.addEventListener('online',()=>registration.update().catch(()=>{}));
      setInterval(()=>{if(!document.hidden)registration.update().catch(()=>{})},60000);
    }).catch(()=>{ /* Online use remains available when offline installation is blocked. */ });
}catch(error){
  loading.textContent='Could not open local storage. Allow website storage for tether and reload. '+(error.message||'');
  loading.setAttribute('role','alert');
}
