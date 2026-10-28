/* Action-owned notes, shared by the Conversation and Tasks drawers. */
window.tetherActionNotes=function(parent,actionId,initial){
 const root=document.createElement('section');root.className='action-notes';root.setAttribute('aria-label','Action notes');
 const make=(tag,cls,text)=>{const n=document.createElement(tag);n.className=cls||'';if(text!==undefined)n.textContent=text;return n};
 const list=make('div','action-notes-list'),status=make('p','reference-error');status.setAttribute('role','status');
 const heading=make('h3','','Notes');root.append(heading,list);parent.append(root);let notes=initial||[];
 const endpoint='/api/actions/'+encodeURIComponent(actionId)+'/notes';
 async function request(url,method,data){const r=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const value=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'Could not save note');window.tetherDataChanged?.(url,method);return value}
 function draw(){list.replaceChildren();for(const note of notes){
  const item=make('article','action-note');item.dataset.noteId=note.id;
  const body=make('p','action-note-body',note.body),meta=make('small','muted',new Date(note.updated_at).toLocaleString());
  const actions=make('div','note-controls'),edit=make('button','secondary small-button','Edit'),remove=make('button','secondary small-button','Delete');edit.type=remove.type='button';actions.append(edit,remove);item.append(body,meta,actions);list.append(item);
  edit.onclick=()=>{const form=make('form','note-edit'),input=make('textarea');input.value=note.body;input.maxLength=20000;input.required=true;input.setAttribute('aria-label','Edit action note');
   const save=make('button','secondary small-button','Save note'),cancel=make('button','secondary small-button','Cancel');save.type='submit';cancel.type='button';cancel.onclick=draw;form.append(input,save,cancel);item.replaceChildren(form);input.focus();
   form.onsubmit=async e=>{e.preventDefault();if(!input.value.trim())return;save.disabled=true;status.textContent='';try{const updated=await request(endpoint+'/'+encodeURIComponent(note.id),'PATCH',{body:input.value});notes=notes.map(n=>n.id===note.id?updated:n);draw();status.textContent='Note saved.'}catch(error){status.textContent=error.message;save.disabled=false}};
  };
  remove.onclick=async()=>{if(!confirm('Delete this note? The action item and its other notes will remain.'))return;remove.disabled=true;status.textContent='';try{await request(endpoint+'/'+encodeURIComponent(note.id),'DELETE');notes=notes.filter(n=>n.id!==note.id);draw();status.textContent='Note deleted.'}catch(error){status.textContent=error.message;remove.disabled=false}};
 }}
 const form=make('form','note-add'),label=make('label','','Add a note'),input=make('textarea');input.required=true;input.maxLength=20000;input.rows=3;input.placeholder='A detail, update, or feedback about this action…';input.setAttribute('aria-label','Add action note');label.append(input);
 const type=make('select');type.setAttribute('aria-label','Action note type');for(const text of ['General note','Meeting note']){const option=make('option','',text);type.append(option)}form.prepend(type);
 const add=make('button','secondary small-button','Add note');add.type='submit';form.append(label,add);root.append(form,status);let noteId=null,noteBody='';
 form.onsubmit=async e=>{e.preventDefault();const text=input.value.trim();if(!text)return;const body=(type.value==='Meeting note'?'Meeting notes\n\n':'')+text;if(body!==noteBody||!noteId){noteId=crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);noteBody=body}add.disabled=true;status.textContent='';try{const note=await request(endpoint,'POST',{body,note_id:noteId});if(!notes.some(n=>n.id===note.id))notes.push(note);noteId=null;input.value='';draw();status.textContent='Note saved.'}catch(error){status.textContent=error.message}finally{add.disabled=false}};
 draw();return root;
};

/* Task notes are stored entries, including notes saved through chat tools. */
window.tetherTaskNotes=function(parent,task){
 const root=document.createElement('section');root.className='action-notes';root.setAttribute('aria-label','Task notes');
 const make=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n};
 root.append(make('h3','Notes'));const list=make('div');root.append(list);
 function draw(){list.replaceChildren();for(const note of (task.entries||[]).filter(e=>e.kind!=='action')){
  const article=make('article');article.className='action-note';const body=make('p',note.body);body.className='action-note-body';article.append(body,make('small',new Date(note.created_at).toLocaleString()));list.append(article)
 }if(!list.childNodes.length)list.append(make('p','No saved notes yet.'))}
 const form=make('form');form.className='note-add';const type=make('select');type.setAttribute('aria-label','Task note type');
 for(const [value,text] of [['general','General note'],['meeting','Meeting note']]){const option=make('option',text);option.value=value;type.append(option)}
 const title=make('input');title.placeholder='Meeting title (optional)';title.setAttribute('aria-label','Meeting title');title.hidden=true;type.onchange=()=>title.hidden=type.value!=='meeting';
 const input=make('textarea');input.required=true;input.maxLength=20000;input.placeholder='Save notes, decisions, or meeting minutes on this task…';input.setAttribute('aria-label','Add task note');
 const save=make('button','Save note');save.className='secondary small-button';save.type='submit';const status=make('p');status.setAttribute('role','status');
 form.append(type,title,input,save,status);root.append(form);parent.append(root);draw();
 form.onsubmit=async event=>{event.preventDefault();if(!input.value.trim())return;save.disabled=true;status.textContent='';
  const body=(type.value==='meeting'?'Meeting notes'+(title.value.trim()?' — '+title.value.trim():'')+'\n\n':'')+input.value.trim();
  try{const url='/api/threads/'+encodeURIComponent(task.id)+'/entries';const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'thought',body})});const note=await response.json();if(!response.ok)throw Error(note.detail||'Could not save note');task.entries.push(note);window.tetherDataChanged?.(url,'POST');input.value='';title.value='';draw();status.textContent='Note saved on this task.'}catch(error){status.textContent=error.message}finally{save.disabled=false}
 };
 return root;
};
