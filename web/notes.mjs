/* Portable Markdown for local commands; the shared screen supplies presentation. */
export const noteText=value=>String(value||'').replace(/[\r\n]/g,' ').replace(/[\\`*_\[\]|]/g,'\\$&');
export function taskTable(tasks,details) {
  const lines=['| Task | Context / next action | When |','| --- | --- | --- |'];
  for(const task of tasks) {
    const full=details?details(task.id):task,actions=(full.entries||[]).filter(e=>e.kind==='action'&&!e.done).map(e=>{
      const schedules=[];
      if(e.due_at)schedules.push('due '+e.due_at.slice(0,10));
      if(e.revisit_at)schedules.push('Bring to attention '+e.revisit_at.slice(0,10));
      return e.body+(schedules.length?' ('+schedules.join('; ')+')':'');
    });
    let context=task.summary||'';
    if(actions.length)context+=(context?' ':'')+'Next: '+actions.join('; ');
    const when=[];
    if(task.due_at)when.push('Due '+task.due_at.slice(0,10));
    if(task.revisit_at)when.push('Bring to attention '+task.revisit_at.slice(0,10));
    if(task.recurrence && task.next_occurrence)when.push('Next occurrence '+task.next_occurrence.slice(0,10));
    if(['waiting','paused','settled'].includes(task.state))when.push({waiting:'Waiting',paused:'Paused',settled:'Done'}[task.state]);
    lines.push(`| [${noteText(task.title)}](/board#task/${encodeURIComponent(task.id)}) | ${noteText(context)} | ${noteText(when.join('; '))} |`);
  }
  return lines.join('\n');
}
export function taskNote(title,tasks,details,limit=25) {
  const lines=['## '+title,''];
  if(!tasks.length)lines.push('Nothing here right now.');
  else {
    lines.push(taskTable(tasks.slice(0,limit),details));
    if(tasks.length>limit)lines.push('',`Showing ${limit} of ${tasks.length} tasks. Open Tasks to see the rest.`);
  }
  return lines.join('\n');
}
export function briefNote(data,details) {
  const sections=['## Daily brief'],seen=new Set();
  for(const [key,title] of [['deadlines','Due dates'],['due','Bring to attention'],['active','In progress'],['waiting','Waiting on']]) {
    const rows=data[key].filter(task=>!seen.has(task.id));if(!rows.length)continue;
    rows.slice(0,15).forEach(task=>seen.add(task.id));
    sections.push(taskNote(title,rows,details,15));
  }
  if(!seen.size)sections.push('No due, active, or waiting tasks in this brief.');
  return sections.join('\n\n');
}
export function checkInNote(task,action,path) {
  const selected=action||task,title=action?.body||task.title;
  const parts=[`[${noteText(title)}](${path})`+(action?` in [${noteText(task.title)}](/board#task/${encodeURIComponent(task.id)})`:'')];
  if(task.summary)parts.push(noteText(task.summary));
  if(action?.notes?.length)parts.push('Latest note: '+noteText(action.notes.at(-1).body));
  const facts=[];
  if(selected.due_at)facts.push(['Due date',selected.due_at.slice(0,10)]);
  for(const [label,value] of [['Bring to attention',selected.revisit_at],['Next occurrence',!action&&task.recurrence?task.next_occurrence:null]])
    if(value)facts.push([label,value.length===10?value:new Date(value).toLocaleString(undefined,{weekday:'short',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'})]);
  if(facts.length)parts.push('| Detail | Value |\n| --- | --- |\n'+facts.map(([label,value])=>`| ${label} | ${noteText(value)} |`).join('\n'));
  parts.push('What is the latest on this '+(action?'action':'task')+'—is it complete, blocked, or still in progress?');
  return parts.join('\n\n');
}
