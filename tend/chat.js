/* The server owns the queue. Closing/navigating this page never cancels a job. */
(() => {
 const chat=document.querySelector('#chat');if(!chat)return;
 const workspace=window.tetherWorkspace||'work';
 const suffix=workspace==='work'?'':'-'+workspace;
 const journalKey='tether-chat-outbox'+suffix,draftKey='tether-chat-draft'+suffix;
 const contextKey='tether-chat-context-'+workspace;
 let contextIds=[];try{const saved=JSON.parse(sessionStorage.getItem(contextKey)||'[]');if(Array.isArray(saved))contextIds=saved.filter(id=>typeof id==='string').slice(0,10)}catch(_){}
 const contextTitles=new Map(),contextBar=el('div','chat-task-context');contextBar.setAttribute('aria-label','Selected task context');
 document.querySelector('#composer').prepend(contextBar);
 const contextStyle=document.createElement('style');contextStyle.textContent='.chat-task-context{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;font-size:12px}.chat-task-context:empty{display:none}.chat-context-chip{display:inline-flex;align-items:center;gap:6px;max-width:100%;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--text)}.chat-context-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:240px}.chat-context-chip button{background:none;border:0;padding:2px;display:flex;color:var(--muted);cursor:pointer}.chat-context-chip button:hover{color:var(--text)}';document.head.append(contextStyle);
 function saveContext(){try{sessionStorage.setItem(contextKey,JSON.stringify(contextIds))}catch(_){}renderContext()}
 function renderContext(){
  contextBar.replaceChildren();if(!contextIds.length)return;
  contextBar.append(el('span','muted','Task context:'));
  for(const id of contextIds){const title=contextTitles.get(id)||'Selected task',chip=el('div','chat-context-chip'),remove=el('button');remove.type='button';remove.title='Remove '+title+' from chat context';remove.setAttribute('aria-label',remove.title);remove.innerHTML='<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>';remove.onclick=()=>{contextIds=contextIds.filter(value=>value!==id);saveContext()};chip.append(el('span','',title),remove);contextBar.append(chip)}
 }
 async function refreshContext(){
  await Promise.all(contextIds.map(async id=>{try{const task=await api('/threads/'+encodeURIComponent(id));contextTitles.set(id,task.title)}catch(_){contextTitles.set(id,'Unavailable task — remove to continue')}}));renderContext();
 }
 const contextURL=new URL(location.href),addedContext=contextURL.searchParams.get('task_context');
 if(addedContext){contextIds=[...new Set([...contextIds,addedContext])].slice(-10);saveContext();contextURL.searchParams.delete('task_context');history.replaceState(history.state,'',contextURL)}
 renderContext();refreshContext();
 let syncing=false,syncAgain=false,timer=null,jobs=[],first=true,submitting=false,jobStamp='';
 let attentionRequest=0,attentionStamp='',attentionTimer=null;
 const nodes=new Map(),pendingNodes=new Map(),sending=new Set(),attentionSending=new Set(),rejected=new Map();
 const inputError=el('p','voice-status');inputError.setAttribute('role','alert');inputError.hidden=true;document.querySelector('#composer').append(inputError);
 function readJournal(){try{return JSON.parse(localStorage.getItem(journalKey)||'{}')}catch(_){return {}}}
 function writeJournal(value){try{localStorage.setItem(journalKey,JSON.stringify(value))}catch(_){}}
 function remember(payload){const value=readJournal();value[payload.request_id]=payload;writeJournal(value)}
 function forget(id){const value=readJournal();delete value[id];writeJournal(value)}
 function newId(){return crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)}
 function messageNode(row){
  let node=nodes.get(row.id);
  if(!node){node=el('div','bubble '+(row.role==='user'?'user':'assistant'));node.dataset.messageId=row.id;nodes.set(row.id,node)}
  if(node.dataset.body!==row.body){node.dataset.body=row.body;node.textContent=row.body;
   if(row.role==='assistant'&&row.html){node.innerHTML=row.html;appendSnapshot(node,row.html);window.TetherNotes?.enhance(node,parseReference)}
  }
  return node;
 }
 function pendingNode(job){
  let node=pendingNodes.get(job.id);if(!node){node=el('div','bubble assistant chat-pending');node.dataset.requestId=job.id;pendingNodes.set(job.id,node)}
  const signature=job.status+JSON.stringify(job.progress)+job.error;
  if(node.dataset.signature===signature)return node;
  node.dataset.signature=signature;node.replaceChildren();node.setAttribute('role','status');
  if(job.status==='error'||job.status==='interrupted'){
   const unchanged=job.changes_saved===false || !job.progress?.length && /^(Enter your API key in Settings|Unlock your saved API key in Settings)/.test(job.error);
   node.append(el('span','retry-error',job.error+(unchanged?' No tasks were changed.':' Changes may have been saved before the failure.')));
   const retry=el('button','retry-icon');retry.type='button';retry.title='Retry this request';retry.setAttribute('aria-label','Retry this request');
   retry.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 11a8 8 0 1 0-2.2 5.5M20 4v7h-7"/></svg>';
   retry.onclick=async()=>{retry.disabled=true;try{await enqueue(job.message,job.context?.kind==='attention'?{task_id:job.context.task_id,action_id:job.context.action_id}:null,job.context?.kind==='task_context'?job.context.task_ids:undefined)}finally{retry.disabled=false}};
   node.append(retry);
  }else{
   node.append(el('div','tend-activity-heading',job.status==='queued'?'Queued…':'Working on your request'));
   if(job.progress?.length){node.append(el('div','tend-activity-current',job.progress.at(-1)));const details=el('details','tend-activity-details');details.append(el('summary','','Show activity'));const log=el('div','tend-activity-log');for(const item of job.progress)log.append(el('div','',item));details.append(log);node.append(details)}
   node.append(el('small','muted','You can switch to Tasks; this request will keep running.'));
  }
  return node;
 }
 function renderState(state){
  const bottom=chat.scrollHeight-chat.scrollTop-chat.clientHeight<100;
  jobs=state.jobs||[];const byUser=new Map(jobs.map(j=>[j.user_message_id,j]));const accepted=new Set(jobs.map(j=>j.id));
  // Tools can save changes before a reply finishes, including a failed reply.
  const stamp=JSON.stringify(jobs.map(j=>[j.id,j.status,j.updated_at,j.progress]));
  if(stamp!==jobStamp){jobStamp=stamp;queueAttention();refreshReferences()}
  const desired=[];
  for(const row of state.messages||[]){desired.push(messageNode(row));const job=byUser.get(row.id);if(job&&job.status!=='done')desired.push(pendingNode(job))}
  desired.push(...(window.tetherLocationCards?.(state.locations)||[]));
  for(const id of accepted)forget(id);
  for(const payload of Object.values(readJournal())){
   if(accepted.has(payload.request_id))continue;
   desired.push(messageNode({id:'outbox-'+payload.request_id,role:'user',body:payload.text||'Checking this attention item…'}));
   desired.push(pendingNode({id:payload.request_id,status:'queued',progress:['Sending your request…']}));
  }
  for(const {payload,error} of rejected.values()){
   desired.push(messageNode({id:'outbox-'+payload.request_id,role:'user',body:payload.text}));
   desired.push(pendingNode({id:payload.request_id,status:'error',error,changes_saved:false}));
  }
  if(!desired.length){if(!chat.querySelector('.welcome')){const welcome=el('div','welcome');welcome.append(el('h1','',"What's on your mind?"),el('p','','Put something down, ask what you’re tracking, or pick up where you left off.'));chat.replaceChildren(welcome)}}
  else{
   // Reconcile stable nodes instead of replacing chat and reloading calendars.
   const wanted=new Set(desired);for(const child of [...chat.children])if(!wanted.has(child))child.remove();
   let previous=null;for(const node of desired){const next=previous?previous.nextSibling:chat.firstChild;if(node!==next)chat.insertBefore(node,next);previous=node}
  }
  if(bottom||first)scrollChat();first=false;
 }
 async function sync(){
  if(syncing){syncAgain=true;return}syncing=true;
  try{const state=await api('/chat/state');renderState(state);for(const p of Object.values(readJournal()))send(p)}
  catch(error){if(first){chat.replaceChildren(el('p','hint','Could not load conversation: '+error.message))}}
  finally{syncing=false;clearTimeout(timer);const delay=syncAgain?0:jobs.some(j=>['queued','running'].includes(j.status))||Object.keys(readJournal()).length?800:10000;syncAgain=false;timer=setTimeout(sync,delay)}
 }
 async function send(payload){
  if(sending.has(payload.request_id))return;sending.add(payload.request_id);
  try{
   const response=await fetch('/api/chat/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   if(!response.ok){const error=await response.json().catch(()=>({}));if(response.status>=400&&response.status<500){
    const message=typeof error.detail==='string'?error.detail:'The message was not accepted. Your text has been kept; edit it and try again.';
    rejected.set(payload.request_id,{payload,error:message});forget(payload.request_id);
    const input=document.querySelector('#message');if(!input.value){input.value=payload.text;try{localStorage.setItem(draftKey,payload.text)}catch(_){}}
    await sync();return;
   }throw Error('Could not confirm delivery; reconnecting…')}
   await response.json();forget(payload.request_id);await sync();
  }catch(error){
   // Reposting an unacknowledged UUID is safe: the server never starts it twice.
   const node=pendingNodes.get(payload.request_id);if(node){node.textContent=error.message;node.dataset.signature=''}
  }finally{sending.delete(payload.request_id)}
 }
 async function enqueue(text,attention=null,selectedContext=contextIds){
  if(!attention&&text.length>50000){inputError.textContent='This message is over 50,000 characters. Split it into smaller messages. Your text has been kept.';inputError.hidden=false;return null}
  inputError.hidden=true;
  if(window.tetherBeforeChat && !await window.tetherBeforeChat(text,attention))return null;
  const payload={request_id:newId(),text,...(attention?{attention}:{task_context:[...selectedContext]})};remember(payload);
  if(chat.querySelector('.welcome'))chat.replaceChildren();
  const user=messageNode({id:'outbox-'+payload.request_id,role:'user',body:text});chat.append(user,pendingNode({id:payload.request_id,status:'queued',progress:['Sending your request…']}));scrollChat();
  send(payload);sync();return payload.request_id;
 }
 async function checkIn(item){
  const target={task_id:item.task_id||item.id,action_id:item.action_id||null};const key=target.task_id+'/'+(target.action_id||'');
  if(attentionSending.has(key)||jobs.some(j=>['queued','running'].includes(j.status)&&j.context?.task_id===target.task_id&&(j.context.action_id||null)===target.action_id))return;
  attentionSending.add(key);
  enqueue('Check in on '+item.title+(item.task_title?' in '+item.task_title:'')+'. Give me the relevant context and ask for my update.',target);
  document.querySelector('#message').focus();setTimeout(()=>attentionSending.delete(key),1200);
 }
 async function reminders(force=false){
  const target=document.querySelector('#due'),request=++attentionRequest;
  try{const data=await api('/attention'+(force?'?force=true':''));if(request!==attentionRequest)return;
   const stamp=JSON.stringify(data.items||[]);if(stamp===attentionStamp)return;attentionStamp=stamp;target.replaceChildren();
   if(!data.items?.length){target.append(el('p','muted','Nothing needs attention right now.'));return}
   for(const item of data.items){const button=el('button','item attention-item');button.type='button';button.dataset.taskId=item.task_id||item.id;if(item.action_id)button.dataset.actionId=item.action_id;
    button.append(el('strong','',item.title),el('small','',[item.task_title,item.reason].filter(Boolean).join(' · ')));
    button.title='Start a check-in about this item';button.onclick=()=>checkIn(item);target.append(button)}
  }catch(error){if(request===attentionRequest&&!target.children.length)target.append(el('p','muted','Attention could not be loaded.'))}
 }
 function queueAttention(){clearTimeout(attentionTimer);attentionTimer=setTimeout(()=>{if(!document.hidden)reminders()},50)}
 function resume(){sync();queueAttention()}
 window.addEventListener('tether:data-changed',()=>{queueAttention();refreshReferences()});
 window.addEventListener('focus',queueAttention);
 // Plain chat and attention clicks use the same durable submission path.
 document.querySelector('#composer').onsubmit=async event=>{
  event.preventDefault();const input=document.querySelector('#message'),text=input.value.trim();if(!text||submitting)return;
  submitting=true;
  try{
   if(!await enqueue(text))return;
   document.querySelector('#command-menu').classList.add('hidden');
   if(input.value.trim()===text){input.value='';try{localStorage.removeItem(draftKey)}catch(_){}}
   input.focus();
  }finally{submitting=false}
 };
 document.querySelector('#refreshAttention').onclick=()=>reminders(true);
 const input=document.querySelector('#message');try{input.value=localStorage.getItem(draftKey)||''}catch(_){}
 input.addEventListener('input',()=>{try{localStorage.setItem(draftKey,input.value)}catch(_){}});
 window.addEventListener('pageshow',resume);document.addEventListener('visibilitychange',()=>{if(!document.hidden)resume()});
 window.addEventListener('online',resume);
 const discuss=new URLSearchParams(location.search).get('discuss');if(discuss&&!input.value){input.value=discuss;input.focus()}
 refreshReferences();sync();reminders();
 // Covers due times and updates from MCP or another process without an event.
 setInterval(()=>{if(!document.hidden)reminders()},3000);
})();
