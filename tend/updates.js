/* Notify open views after a task write commits. No task content is broadcast. */
(() => {
 const name='tether-data-updates:'+(window.TETHER_CONFIG?.base||'/');
 const notify=()=>window.dispatchEvent(new Event('tether:data-changed'));
 let channel;
 try{if('BroadcastChannel' in window){channel=new BroadcastChannel(name);channel.onmessage=event=>{if(event.data==='changed')notify()}}}catch(_){}
 window.addEventListener('storage',event=>{if(event.key===name)notify()});
 window.tetherDataChanged=(path,method)=>{
  if(!['POST','PATCH','DELETE','PUT'].includes(method)||!/(?:^|\/)(?:threads|actions|entries|import)(?:\/|$)/.test(path))return;
  notify();
  if(channel)channel.postMessage('changed');
  else try{localStorage.setItem(name,Date.now()+'-'+Math.random())}catch(_){}
 };
})();
