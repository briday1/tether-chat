/* Calendar recurrence is projected, never materialized as duplicate tasks. */
function utc(year,month,date,hour=0,minute=0,second=0,ms=0){const d=new Date(0);d.setUTCFullYear(year,month,date);d.setUTCHours(hour,minute,second,ms);return +d}
const DAY=86400000, monthSteps={monthly:1,quarterly:3,yearly:12};
export function calendarDate(value){
  if(typeof value!=='string'||!/^\d{4}-\d\d-\d\d$/.test(value))throw new Error('Use a date in YYYY-MM-DD format');
  const d=new Date(value+'T00:00:00Z');if(!Number.isFinite(+d)||d.getUTCFullYear()<1||d.toISOString().slice(0,10)!==value)throw new Error('Invalid calendar date');return value;
}
export function recurrenceValue(value){
  if(value===null||value===undefined||value==='')return null;
  if(typeof value==='string'&&value.length===10)return calendarDate(value);
  if(typeof value!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d{1,6})?)?(?:Z|[+-]\d\d:\d\d)$/.test(value)||!Number.isFinite(Date.parse(value)))throw new Error('Use an ISO date or a date/time including its timezone');
  calendarDate(value.slice(0,10));const parts=value.slice(11).match(/^(\d\d):(\d\d)(?::(\d\d))?/);if(Number(parts[1])>23||Number(parts[2])>59||Number(parts[3]||0)>59)throw new Error('Invalid recurrence time');return value;
}
export function recurrenceZone(value){if(value===null||value===undefined)return null;if(typeof value!=='string'||value.length>100)throw new Error('Invalid recurrence timezone');try{new Intl.DateTimeFormat('en',{timeZone:value}).format()}catch(_){throw new Error('Invalid recurrence timezone')}return value}
const pad=n=>String(n).padStart(2,'0');
const formatters=new Map();
function wall(instant,zone){if(!formatters.has(zone)){if(formatters.size>64)formatters.clear();formatters.set(zone,new Intl.DateTimeFormat('en-CA',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}))}const parts=formatters.get(zone).formatToParts(new Date(instant));const p=Object.fromEntries(parts.map(p=>[p.type,p.value]));return [Number(p.year),Number(p.month),Number(p.day),Number(p.hour),Number(p.minute),Number(p.second),new Date(instant).getUTCMilliseconds()]}
const wallMs=p=>utc(p[0],p[1]-1,p[2],p[3]||0,p[4]||0,p[5]||0,p[6]||0);
function zoned(p,zone){
  const target=wallMs(p),offsets=new Set();for(const shift of [-2,-1,0,1,2]){const instant=target+shift*DAY;offsets.add(wallMs(wall(instant,zone))-instant)}
  const choices=[...offsets].map(offset=>target-offset).sort((a,b)=>a-b),exact=choices.filter(instant=>wallMs(wall(instant,zone))===target);
  // Earlier fold; spring gaps move forward by the gap, matching calendar wall-time intent.
  return exact[0]??choices.filter(instant=>wallMs(wall(instant,zone))>target).sort((a,b)=>wallMs(wall(a,zone))-wallMs(wall(b,zone)))[0];
}
function config(task){
  const anchor=task.recurrence_anchor||task.next_occurrence;if(!anchor)return null;
  const dateOnly=anchor.length===10,zone=task.recurrence_timezone||null;
  const offset=dateOnly?'Z':(anchor.match(/(Z|[+-]\d\d:\d\d)$/)||[])[1]||'Z';
  const p=zone&&!dateOnly?wall(Date.parse(anchor),zone):[...anchor.slice(0,10).split('-').map(Number),...(dateOnly?[0,0,0]:anchor.slice(11).match(/^(\d\d):(\d\d)(?::(\d\d))?/).slice(1).map(x=>Number(x||0))),dateOnly?0:new Date(anchor).getUTCMilliseconds()];
  return {anchor,dateOnly,zone,offset,p};
}
function occurrence(c,frequency,index){
  if(index===0)return {value:c.anchor,date:scheduleDay(c.anchor,c.zone)};
  const p=[...c.p],months=monthSteps[frequency];
  if(months){const d=new Date(utc(p[0],p[1]-1+months*index,1));p[0]=d.getUTCFullYear();p[1]=d.getUTCMonth()+1;p[2]=Math.min(c.p[2],new Date(utc(p[0],p[1],0)).getUTCDate())}
  else if(frequency==='daily'||frequency==='weekly'){const d=new Date(utc(p[0],p[1]-1,p[2]+index*(frequency==='daily'?1:7)));p[0]=d.getUTCFullYear();p[1]=d.getUTCMonth()+1;p[2]=d.getUTCDate()}
  else throw new Error('Invalid recurrence');
  if(p[0]>9999||p[0]<1)return null;
  const date=`${String(p[0]).padStart(4,'0')}-${pad(p[1])}-${pad(p[2])}`;
  if(c.dateOnly)return {value:date,date};
  const value=c.zone?new Date(zoned(p,c.zone)).toISOString():`${date}T${pad(p[3])}:${pad(p[4])}:${pad(p[5])}.${String(p[6]).padStart(3,'0')}${c.offset}`;
  return {value,date:c.zone?scheduleDay(value,c.zone):date};
}
function estimate(c,frequency,value){const p=value.slice(0,10).split('-').map(Number);return Math.max(0,(monthSteps[frequency]?Math.floor(((p[0]-c.p[0])*12+p[1]-c.p[1])/monthSteps[frequency]):Math.floor((utc(p[0],p[1]-1,p[2])-utc(c.p[0],c.p[1]-1,c.p[2]))/DAY/(frequency==='weekly'?7:1)))-3)}
const instant=value=>Date.parse(value.length===10?value+'T00:00:00Z':value);
export function occurrenceDay(value){if(value.length===10)return value;const d=new Date(value);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`}
export function occurrences(task,start,end){
  if(!task.recurrence||!task.next_occurrence||task.state==='settled'||task.archived_at)return [];
  const c=config(task),result=[],minimum=instant(task.next_occurrence);let index=estimate(c,task.recurrence,start);
  // At most the visible range plus a small timezone/index margin; skip old history arithmetically.
  for(let count=0;count<380;count++,index++){
    const item=occurrence(c,task.recurrence,index);if(!item)break;if(task.recurrence_end&&item.date>task.recurrence_end)break;
    const date=occurrenceDay(item.value);if(date>end)break;
    if(date>=start&&instant(item.value)>=minimum)result.push({...item,date});
  }return result;
}
export function nextOccurrence(task,after){
  const c=config(task);if(!c)return null;if(c.dateOnly&&after.length!==10)after=occurrenceDay(after);let index=estimate(c,task.recurrence,instant(after)>instant(task.next_occurrence)?after:task.next_occurrence),minimum=Math.max(instant(after),instant(task.next_occurrence));
  for(let count=0;count<12;count++,index++){
    const item=occurrence(c,task.recurrence,index);if(!item)return null;if(task.recurrence_end&&item.date>task.recurrence_end)return null;
    if(instant(item.value)>minimum)return item.value;
  }throw new Error('Cannot advance recurrence');
}
export function scheduleDay(value,zone){if(value.length===10)return value;if(!zone)return value.slice(0,10);const p=wall(Date.parse(value),zone);return `${String(p[0]).padStart(4,'0')}-${pad(p[1])}-${pad(p[2])}`}

export function recurrenceDue(task,now){if(!task.next_occurrence)return false;return task.next_occurrence.length===10?task.next_occurrence<=occurrenceDay(now):Date.parse(task.next_occurrence)<=Date.parse(now)}
