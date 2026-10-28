import {createRuntime} from './runtime.mjs';
import {prepareLaunch} from './launch.mjs';
const config=window.TETHER_CONFIG,frame=document.querySelector('#app-frame'),loading=document.querySelector('#loading');
let current='',installPrompt=null;
// The shell owns history. Child-frame replacements must not add joint entries.
const navigateFrame=url=>frame.contentWindow.location.replace(url);
let workspace=new URLSearchParams(location.search).get('workspace')==='home'?'home':'work';
const runtimes=new Map();
let workspaceRevision=0;
function runtimeFor(mode){
  if(!runtimes.has(mode))runtimes.set(mode,createRuntime({config:{...config,workspace:mode}}));
  return runtimes.get(mode);
}
window.tetherSwitchWorkspace=async(mode,{historyChange=true}={})=>{
  if(!['work','home'].includes(mode))return;
  const revision=++workspaceRevision;navigateFrame('about:blank');
  workspace=mode;
  const url=new URL(location.href);url.searchParams.set('workspace',mode);url.hash='';url.searchParams.delete('discuss');url.searchParams.delete('task_context');
  if(historyChange)history.pushState({},'',url);
  window.tetherReady=runtimeFor(mode);
  const runtime=await window.tetherReady;if(revision!==workspaceRevision)return;window.tetherFetch=runtime.fetch;window.tetherNotify=()=>runtime.notifications();
  current=pageURL();navigateFrame(current);
};
// Pin this document and all of its screens to one installed bundle.
const sessionURL=new URL(location.href);sessionURL.searchParams.set('release',config.version);
history.replaceState({},'',sessionURL.pathname+sessionURL.search+sessionURL.hash);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event});
window.tetherInstall=async()=>{if(!installPrompt)return false;await installPrompt.prompt();installPrompt=null;return true};
function pageURL(){
  const query=new URLSearchParams(location.search),view=query.get('view')||'conversation';query.delete('view');query.set('release',config.version);query.set('workspace',workspace);
  const page={sharing:'drive-sharing.html',board:'board.html',snapshots:'snapshots.html',display:'display.html',conversation:'conversation.html'}[view]||'conversation.html';
  return config.base+page+(query.size?'?'+query:'')+location.hash;
}
function shellURL(url){
  const page=url.pathname.slice(config.base.length),query=new URLSearchParams(url.search);query.set('release',config.version);query.set('workspace',workspace);
  if(page==='drive-sharing.html')query.set('view','sharing');else if(page==='display.html')query.set('view','display');else if(page==='board.html')query.set('view','board');else if(page==='snapshots.html')query.set('view','snapshots');else query.delete('view');
  return config.base+(query.size?'?'+query:'')+url.hash;
}
window.tetherNavigate=(href,{replace=false}={})=>{
  const url=new URL(href,location.origin);
  if(url.origin!==location.origin || !['conversation.html','board.html','snapshots.html','display.html','drive-sharing.html'].some(page=>url.pathname===config.base+page))return;
  url.searchParams.set('release',config.version);url.searchParams.set('workspace',workspace);
  const next=url.pathname+url.search+url.hash;if(current===next)return;
  history[replace?'replaceState':'pushState']({},'',shellURL(url));current=next;navigateFrame(next);
};
window.tetherSyncRoute=href=>{
  const url=new URL(href,location.origin);
  if(url.origin!==location.origin || !['conversation.html','board.html','snapshots.html','display.html','drive-sharing.html'].some(page=>url.pathname===config.base+page))return;
  url.searchParams.set('release',config.version);url.searchParams.set('workspace',workspace);
  const next=url.pathname+url.search+url.hash;
  if(current!==next){current=next;history.replaceState({},'',shellURL(url))}
};
window.addEventListener('popstate',()=>{const mode=new URLSearchParams(location.search).get('workspace')==='home'?'home':'work';if(mode!==workspace){window.tetherSwitchWorkspace(mode,{historyChange:false});return}const next=pageURL();if(next!==current){current=next;navigateFrame(next)}});
window.tetherReady=prepareLaunch(config).then(open=>open?runtimeFor(workspace):new Promise(()=>{}));
try{
  const runtime=await window.tetherReady;window.tetherFetch=runtime.fetch;
  window.tetherNotify=()=>runtime.notifications();
  current=pageURL();navigateFrame(current);frame.hidden=false;loading.hidden=true;
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
}catch(error){
  loading.textContent='Could not open local storage. Allow website storage for tether and reload. '+(error.message||'');
  loading.setAttribute('role','alert');
}
