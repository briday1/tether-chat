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
 const add=make('button','secondary small-button','Add note');add.type='submit';form.append(label,add);root.append(form,status);let noteId=null,noteBody='';
 form.onsubmit=async e=>{e.preventDefault();const body=input.value.trim();if(!body)return;if(body!==noteBody||!noteId){noteId=crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);noteBody=body}add.disabled=true;status.textContent='';try{const note=await request(endpoint,'POST',{body,note_id:noteId});if(!notes.some(n=>n.id===note.id))notes.push(note);noteId=null;input.value='';draw();status.textContent='Note saved.'}catch(error){status.textContent=error.message}finally{add.disabled=false}};
 draw();return root;
};
