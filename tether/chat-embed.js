/* Display reuses the ordinary conversation, draft, queue, and voice controls. */
(() => {
  if(parent===window||new URLSearchParams(location.search).get('chat')!=='display')return;
  document.documentElement.setAttribute('data-chat-embed','');
  const style=document.createElement('style');
  style.textContent=`html[data-chat-embed] .topnav,html[data-chat-embed] #right{display:none!important}
html[data-chat-embed] .app{height:100dvh!important;display:flex!important}
html[data-chat-embed] .main{width:100%;min-width:0;flex:1}
html[data-chat-embed] #chat{padding:18px;min-height:0}
html[data-chat-embed] #composer{padding:10px 14px 14px;flex-shrink:0}
html[data-chat-embed] .settings{top:0!important}html[data-chat-embed] #settingsBackdrop{inset:0!important}
html[data-chat-embed] .welcome h1{font-size:24px}html[data-chat-embed] .bubble{max-width:95%}`;
  document.head.append(style);
  const tell=type=>parent.postMessage({type},location.origin);
  function theme(){try{const value=parent.document.documentElement.dataset.theme;if(value)document.documentElement.dataset.theme=value}catch(_){}}
  window.addEventListener('message',event=>{
    if(event.source!==parent||event.origin!==location.origin)return;
    if(event.data?.type==='tether:chat-hide')window.dispatchEvent(new Event('tether:voice-suspend'));
    if(event.data?.type==='tether:chat-focus'){theme();document.querySelector('#message')?.focus()}
  });
  document.addEventListener('keydown',event=>{
    // Let task/settings drawers and slash-command menus consume their own Escape.
    if(event.key==='Escape'&&!event.defaultPrevented){
      const open=document.querySelector('#settings:not(.hidden),#chatSelection:not(.hidden),#command-menu:not(.hidden)');
      if(!open){event.preventDefault();event.stopPropagation();tell('tether:chat-close')}
    }
  },true);
  window.addEventListener('tether:data-changed',()=>tell('tether:chat-changed'));
  window.addEventListener('tether:chat-state-changed',()=>tell('tether:chat-changed'));
  document.addEventListener('DOMContentLoaded',()=>{theme();tell('tether:chat-ready')});
})();
