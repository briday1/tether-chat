/* One retained conversation frame: hiding it never cancels an accepted request. */
(() => {
  const style=document.createElement('style');style.textContent=`
#display-quick-chat{position:fixed;right:24px;bottom:22px;z-index:5;display:flex;align-items:center;gap:8px;padding:12px 18px;border:1px solid var(--line);border-radius:24px;background:var(--paper);color:var(--text);box-shadow:0 4px 20px #0002;font:inherit;cursor:pointer}
#display-chat-dialog{padding:0;border:1px solid var(--line);border-radius:16px;width:min(680px,calc(100vw - 48px));height:min(660px,76dvh);max-height:calc(100dvh - 32px);background:var(--paper);color:var(--text);box-shadow:0 12px 60px #0003;overflow:hidden}
#display-chat-dialog[open]{display:flex;flex-direction:column}#display-chat-dialog::backdrop{background:#0002}
.display-chat-heading{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line);gap:10px}.display-chat-heading strong{font-size:16px}.display-chat-heading small{color:var(--muted);font-size:12px}.display-chat-heading button{display:grid;place-items:center;width:32px;height:32px;padding:0;border:0;border-radius:7px;background:var(--soft);color:var(--text);cursor:pointer}
#display-chat-frame{border:0;display:block;width:100%;flex:1;min-height:0;background:var(--paper)}
@media(max-width:600px){#display-quick-chat{right:14px;bottom:14px}#display-chat-dialog{width:100%;max-width:100%;height:85dvh;max-height:100dvh;margin:auto 0 0;border-radius:16px 16px 0 0}.display-chat-heading small{display:none}}
`;document.head.append(style);
  const button=document.createElement('button');button.id='display-quick-chat';button.type='button';button.textContent='Quick chat';button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls','display-chat-dialog');
  const dialog=document.createElement('dialog');dialog.id='display-chat-dialog';dialog.setAttribute('aria-label','Quick chat');
  dialog.innerHTML='<header class="display-chat-heading"><strong>Quick chat</strong><small>Requests keep running when closed</small><button type="button" aria-label="Close quick chat"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button></header><iframe id="display-chat-frame" title="Conversation with tether"></iframe>';
  document.body.append(button,dialog);
  const frame=dialog.querySelector('iframe');let loaded=false;
  const message=type=>frame.contentWindow?.postMessage({type},location.origin);
  function dismiss(){if(!dialog.open)return;message('tether:chat-hide');dialog.close();button.focus();window.dispatchEvent(new Event('tether:data-changed'))}
  function close(){dismiss();if(history.state?.tetherDisplayOverlay==='chat'){button.disabled=true;history.back()}}
  function open(push=true){
    if(dialog.open)return;
    if(push)history.pushState({...history.state,tetherDisplayOverlay:'chat'},'',location.href);
    dialog.showModal();
    if(!loaded){loaded=true;frame.src='/?chat=display'}else message('tether:chat-focus');
  }
  button.onclick=()=>open();
  dialog.querySelector('button').onclick=close;
  dialog.addEventListener('cancel',event=>{event.preventDefault();close()});
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)close()}});
  window.addEventListener('popstate',()=>{button.disabled=false;if(history.state?.tetherDisplayOverlay==='chat')open(false);else{dismiss();button.focus()}});
  window.addEventListener('message',event=>{
    if(event.source!==frame.contentWindow||event.origin!==location.origin)return;
    if(event.data?.type==='tether:chat-close')close();
    if(event.data?.type==='tether:chat-ready'&&dialog.open)message('tether:chat-focus');
    if(event.data?.type==='tether:chat-changed')window.dispatchEvent(new Event('tether:data-changed'));
  });
  window.addEventListener('pagehide',()=>message('tether:chat-hide'));
})();
