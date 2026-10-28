/* Shared Note presentation. Stored Markdown and reference behavior stay intact. */
(() => {
 function enhance(root, parseReference) {
  for(const table of root.querySelectorAll('table:not(.note-table)')) {
   const headers=[...table.querySelectorAll('thead th')],labels=headers.map(cell=>cell.textContent.trim());
   table.classList.add('note-table');table.setAttribute('role','table');
   const rows=/^(tasks?|actions?|items?|categor(?:y|ies))$/i.test(labels[0]||'');
   if(rows)table.classList.add('note-rows');
   if(/^actions?$/i.test(labels[0]||''))table.classList.add('note-actions');
   if(/^(detail|field)$/i.test(labels[0]||''))table.classList.add('note-facts');
   const columns=document.createElement('colgroup');
   for(const label of labels){const column=document.createElement('col');if(rows && /^(when|due|date|timing|status)$/i.test(label))column.className='note-when';columns.append(column)}
   table.prepend(columns);
   for(const tr of table.querySelectorAll('tr')) {
    tr.setAttribute('role','row');
    [...tr.children].forEach((cell,index)=>{
     cell.setAttribute('role',cell.tagName==='TH'?'columnheader':'cell');
     cell.dataset.label=labels[index]||'';
     if(index>0)cell.classList.add('note-context');
     if(rows && index>0 && /^(when|due|date|timing|status)$/i.test(labels[index]||''))cell.classList.add('note-when');
    });
   }
   const wrapper=document.createElement('div');wrapper.className='note-table-wrap';
   table.before(wrapper);wrapper.append(table);
  }
  // Providers can still return ordinary Markdown. Give task-linked lists the
  // same feel, without guessing dates, changing text, or flattening subitems.
  if(!parseReference)return;
  for(const list of root.querySelectorAll('ul:not(.note-list)')) {
   if(list.closest('.note-list'))continue;
   const items=[...list.children];if(!items.length)continue;
   const links=items.map(item=>{
    const link=[...item.querySelectorAll('a[href]')].find(a=>parseReference(a.getAttribute('href')));
    if(!link)return null;
    const before=document.createRange();before.selectNodeContents(item);before.setEndBefore(link);
    return before.toString().trim()?null:link;
   });
   if(links.some(link=>!link))continue;
   list.classList.add('note-list');
   items.forEach((item,index)=>{
    const range=document.createRange();range.selectNodeContents(item);range.setStartAfter(links[index]);
    const detail=document.createElement('div');detail.className='note-list-detail';detail.append(range.extractContents());
    if(detail.textContent.trim())item.append(detail);
   });
  }
 }
 window.TetherNotes={enhance};
})();
