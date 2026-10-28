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
  window.tetherUpdateApp=async()=>{
    if(navigator.onLine===false)throw Error('Connect to the internet to update tether.');
    await frame.contentWindow?.tetherPrepareUpdate?.();
    const response=await runtime.fetch(config.base+'api/chat/state'),state=await response.json();
    if((state.jobs||[]).some(job=>['running','queued'].includes(job.status)))throw Error('Finish the current chat request, then update the app.');
    location.assign(config.base+'update.html?check='+Date.now());
  };
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
      const ready=()=>{window.tetherUpdateAvailable=!!registration.waiting;try{frame.contentWindow.dispatchEvent(new Event('tether:update-available'))}catch(_){}};
      const watch=()=>{registration.installing?.addEventListener('statechange',ready);ready()};
      registration.addEventListener('updatefound',watch);watch();
      let checked=Date.now();
      document.addEventListener('visibilitychange',()=>{
        if(!document.hidden && Date.now()-checked>60000){checked=Date.now();registration.update().catch(()=>{})}
      });
    }).catch(()=>{ /* Online use remains available when offline installation is blocked. */ });
}catch(error){
  loading.textContent='Could not open local storage. Allow website storage for tether and reload. '+(error.message||'');
  loading.setAttribute('role','alert');
}
