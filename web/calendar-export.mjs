import {escapeHTML} from './render.mjs';
const palette=['#3279c7','#bd4a69','#478d57','#b87527','#8058bc','#168d99','#c0523e','#6b7d27'];
function color(name){let hash=0;for(const c of name.toLowerCase())hash=(Math.imul(hash,31)+c.charCodeAt(0))>>>0;return palette[hash%palette.length]}
const iso=d=>d.toISOString().slice(0,10);
function wrap(text,width,context){
  const lines=[];let line='';
  for(const word of String(text).split(/\s+/)){
    const next=line?line+' '+word:word;
    if(context.measureText(next).width>width && line){lines.push(line);line=word}else line=next;
    while(context.measureText(line).width>width && line.length>1){
      let end=line.length-1;while(end>1 && context.measureText(line.slice(0,end)).width>width)end--;
      lines.push(line.slice(0,end));line=line.slice(end);
    }
  }
  if(line)lines.push(line);return lines;
}
export function calendarSVG(data,theme={}){
  const weekStart=data.week_start??1,order=Array.from({length:7},(_,i)=>(weekStart+i)%7);
  const days=data.days,byDate=new Map(days.map(d=>[d.date,d])),single=days.length===1;
  const weekends=days.some(d=>[0,6].includes(new Date(d.date+'T12:00:00Z').getUTCDay()) && (d.tasks.length||d.activity.length));
  const columns=single?1:weekends?7:5,width=1100,gap=8,cellWidth=(width-gap*(columns-1))/columns;
  const start=new Date(data.start+'T00:00:00Z'),end=new Date(data.end+'T00:00:00Z');
  if(!single){start.setUTCDate(start.getUTCDate()-(start.getUTCDay()-weekStart+7)%7);end.setUTCDate(end.getUTCDate()+6-(end.getUTCDay()-weekStart+7)%7)}
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d');context.font='13px sans-serif';
  const cells=[];for(let d=new Date(start);d<=end;d.setUTCDate(d.getUTCDate()+1)){
    if(!weekends&&!single&&[0,6].includes(d.getUTCDay()))continue;
    const record=byDate.get(iso(d)),items=record?[...record.tasks.map(t=>({text:(t.schedule_label?t.schedule_label+': ':'')+t.title,names:t.categories||[t.category||'Unsorted']})),
      ...record.activity.map(a=>({text:a.kind+': '+a.body,names:a.categories||[a.category||'Unsorted']}))]:[];
    const cards=items.map(item=>({...item,lines:wrap(item.text,cellWidth-24,context),labels:wrap(item.names.join(' · '),cellWidth-24,context)}));
    cells.push({number:d.getUTCDate(),outside:!record,cards,height:Math.max(95,35+cards.reduce((n,c)=>n+12+(c.lines.length+c.labels.length)*17+7,0))});
  }
  const text=theme.text||'#263d30',muted=theme.muted||'#708372',line=theme.line||'#d7e1d5',paper=theme.paper||'#ffffff';
  const parts=[`<text x="0" y="18" fill="${escapeHTML(muted)}" font-size="14">${data.start} — ${data.end}</text>`];
  if(!single)for(const [i,name] of order.filter(d=>columns===7||d>0&&d<6).map(d=>['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][d]).entries())
    parts.push(`<text x="${i*(cellWidth+gap)+8}" y="43" fill="${escapeHTML(muted)}" font-size="12">${name}</text>`);
  let top=single?33:55;
  for(let offset=0;offset<cells.length;offset+=columns){
    const row=cells.slice(offset,offset+columns),height=Math.max(...row.map(c=>c.height));
    for(const [column,cell] of row.entries()){
      const left=column*(cellWidth+gap);parts.push(`<g opacity="${cell.outside?'.4':'1'}"><rect x="${left+.5}" y="${top+.5}" width="${cellWidth-1}" height="${height-1}" rx="4" fill="none" stroke="${escapeHTML(line)}"/><text x="${left+8}" y="${top+19}" font-size="12" fill="${escapeHTML(muted)}">${cell.number}</text>`);
      let y=top+29;
      for(const card of cell.cards){const h=12+(card.lines.length+card.labels.length)*17,c=color(card.names[0]);
        parts.push(`<rect x="${left+6}" y="${y}" width="${cellWidth-12}" height="${h}" rx="3" fill="${escapeHTML(paper)}"/><rect x="${left+6}" y="${y}" width="${cellWidth-12}" height="${h}" rx="3" fill="${c}" fill-opacity=".13"/>`);
        let baseline=y+17;for(const s of card.lines){parts.push(`<text x="${left+12}" y="${baseline}" font-size="13" fill="${escapeHTML(text)}">${escapeHTML(s)}</text>`);baseline+=17}
        for(const s of card.labels){parts.push(`<text x="${left+12}" y="${baseline}" font-size="11" fill="${escapeHTML(muted)}">${escapeHTML(s)}</text>`);baseline+=17}
        y+=h+7;
      }parts.push('</g>');
    }top+=height+gap;
  }
  return {width,height:top,svg:`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${top}" viewBox="0 0 ${width} ${top}" font-family="sans-serif">${parts.join('')}</svg>`};
}
window.tetherExportCalendar=async(data,format)=>{
  if(!data){document.querySelector('#error').textContent='The calendar is still loading.';return}
  try{
    const styles=getComputedStyle(document.documentElement),theme=Object.fromEntries(['text','muted','line','paper'].map(k=>[k,styles.getPropertyValue('--'+k).trim()]));
    const result=calendarSVG(data,theme);let blob=new Blob([result.svg],{type:'image/svg+xml'});
    if(format==='png'){
      if(result.width*result.height*4>32000000)throw Error('This calendar is too large for a phone PNG. Download SVG or choose a shorter range.');
      const image=new Image(),url=URL.createObjectURL(blob);
      try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('Could not render calendar image'));image.src=url});
        const canvas=document.createElement('canvas');canvas.width=result.width*2;canvas.height=result.height*2;
        canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
        blob=await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(Error('Could not create PNG')),'image/png'));
      }finally{URL.revokeObjectURL(url)}
    }
    await window.tetherDownload(blob,`tether-${data.start}-${data.end}.${format}`);document.querySelector('#error').textContent='';
  }catch(error){document.querySelector('#error').textContent=error.message}
};
