/* Saved defaults and deterministic reminder choices; no provider requests. */
export const DEFAULT_PREFERENCES={week_start:1,morning_time:'09:00',night_time:'21:00'};
export function preferences(value={}){
  if(!value || typeof value!=='object' || Array.isArray(value))throw Error('Preferences must be an object');
  if(Object.keys(value).some(key=>!(key in DEFAULT_PREFERENCES)))throw Error('Unknown reminder preference');
  const result={...DEFAULT_PREFERENCES,...value};
  if(!Number.isInteger(result.week_start)||result.week_start<0||result.week_start>6)throw Error('Choose a beginning-of-week reminder day');
  for(const key of ['morning_time','night_time'])if(typeof result[key]!=='string'||!/^([01]\d|2[0-3]):[0-5]\d$/.test(result[key]))throw Error('Use a time in HH:MM format');
  return result;
}
const days=['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
export function resolveReminder(value,saved={},reference=new Date()){
  if(value===null||value===undefined||value==='')return null;
  if(typeof value!=='string')throw Error('Use a reminder date or a period such as next week');
  const p=preferences(saved),now=new Date(reference),text=value.trim().toLowerCase();
  if(!Number.isFinite(+now))throw Error('Invalid current date');
  let time=p.morning_time;
  if(/\b(night|tonight)\b/.test(text))time=p.night_time;
  else if(/\bevening\b/.test(text))time='18:00';
  else if(/\bafternoon\b/.test(text))time='13:00';
  else if(/\bnoon\b/.test(text))time='12:00';
  const explicit=text.match(/\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/)||text.match(/\bat\s+(\d{1,2})(?::(\d{2}))?\b/)||text.match(/\b(\d{1,2}):(\d{2})\b/);
  if(explicit){let hour=Number(explicit[1]),minute=Number(explicit[2]||0);if(explicit[3])hour=hour%12+(explicit[3]==='pm'?12:0);
    if(hour>23||minute>59)throw Error('Invalid reminder time');time=String(hour).padStart(2,'0')+':'+String(minute).padStart(2,'0')}
  const [hour,minute]=time.split(':').map(Number);
  const wall=(year,month,day)=>new Date(year,month,day,hour,minute,0,0);
  const today=()=>wall(now.getFullYear(),now.getMonth(),now.getDate());
  if(/^\d{4}-\d\d-\d\d$/.test(text)){
    const [y,m,d]=text.split('-').map(Number),date=wall(y,m-1,d);
    if(date.getFullYear()!==y||date.getMonth()!==m-1||date.getDate()!==d)throw Error('Invalid reminder date');return date.toISOString();
  }
  if(/^\d{4}-\d\d-\d\dT/i.test(value.trim())){const date=new Date(value);if(!Number.isFinite(+date))throw Error('Invalid reminder date');return date.toISOString()}
  const explicitDay=text.match(/\b\d{4}-\d\d-\d\d\b/);
  if(explicitDay)return resolveReminder(explicitDay[0],{...p,morning_time:time},reference);
  let date;
  const weekday=days.findIndex(day=>new RegExp('\\b'+day+'\\b').test(text));
  const relative=text.match(/\bin\s+(a|an|one|two|three|four|\d+)\s+(minute|hour|day|week|month|year)s?\b/);
  if(relative){
    const amount={a:1,an:1,one:1,two:2,three:3,four:4}[relative[1]]??Number(relative[1]),unit=relative[2];
    if(amount<1||amount>1000)throw Error('Use a reminder interval from 1 to 1000');
    if(unit==='minute'||unit==='hour')return new Date(+now+amount*(unit==='hour'?3600000:60000)).toISOString();
    date=today();
    if(unit==='day'||unit==='week')date.setDate(date.getDate()+amount*(unit==='week'?7:1));
    else{const day=date.getDate();date.setDate(1);date.setMonth(date.getMonth()+amount*(unit==='year'?12:1));date.setDate(Math.min(day,new Date(date.getFullYear(),date.getMonth()+1,0).getDate()))}
  }else if(/\btomorrow\b|\bnext day\b/.test(text)||text==='day')date=wall(now.getFullYear(),now.getMonth(),now.getDate()+1);
  else if(/\b(?:next|this) week\b/.test(text)||text==='week'){
    date=today();const offset=/\bthis week\b/.test(text)?0:7;
    // Explicit weekdays use the Sunday–Saturday calendar, not the reminder default.
    date.setDate(date.getDate()+(weekday>=0?-date.getDay()+offset+weekday:-(date.getDay()-p.week_start+7)%7+offset));
  }else if(/\b(?:next|this) month\b/.test(text)||text==='month')date=wall(now.getFullYear(),now.getMonth()+(/\bthis month\b/.test(text)?0:1),1);
  else if(/\b(?:next|this) year\b/.test(text)||text==='year')date=wall(now.getFullYear()+(/\bthis year\b/.test(text)?0:1),0,1);
  else{
    if(weekday>=0){date=today();let offset=(weekday-date.getDay()+7)%7;if(offset===0 && /\bnext\b/.test(text))offset=7;date.setDate(date.getDate()+offset);if(+date<=+now)date.setDate(date.getDate()+7)}
    else if(/\b(today|morning|night|tonight|evening|afternoon|soon)\b/.test(text))date=today();
    else throw Error('Use a date or a period such as tomorrow, next week, next month, or next year');
  }
  if(+date<=+now)date=wall(now.getFullYear(),now.getMonth(),now.getDate()+1);
  return date.toISOString();
}
export function reminderIntent(text){
  if(!/\b(remind|reminder|bring.{0,12}attention|follow up|check back)\b/i.test(text))return null;
  if(/\b\d{4}-\d\d-\d\d\b/.test(text))return text;
  if(/\b(?:next|this) week\b/i.test(text)&&days.some(day=>new RegExp('\\b'+day+'\\b','i').test(text)))return text;
  return text.match(/\bin\s+(?:a|an|one|two|three|four|\d+)\s+(?:minute|hour|day|week|month|year)s?(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?/i)?.[0]
    ||text.match(/\b(?:next|this)\s+(?:day|week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?/i)?.[0]
    ||text.match(/\b(?:today|tomorrow|tonight)(?:\s+(?:in the )?(?:morning|night|evening|afternoon))?(?:\s+at\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?)?/i)?.[0]||null;
}
export function decisionFollowup(text){return /^(?:(?:please|just|ok|okay|then)\s+)*(?:figure (?:it|that) out|use your (?:best )?judg(?:e)?ment|you (?:decide|choose|pick)|pick (?:one|a day|a time|a category)|do (?:it|that)|go ahead|make it\b|put it\b|move it\b|change it\b|schedule it\b|yes\b)/i.test(text.trim())}
export function taskKey(title){return title.normalize('NFKC').toLowerCase().replace(/\bdental\b/g,'dentist').replace(/\bappt\b/g,'appointment').replace(/[^\p{L}\p{N}\s]/gu,' ').split(/\s+/).filter(word=>word&&!new Set(['a','an','the','my','me','to','please','remind','reminder','make','book','schedule']).has(word)).sort().join(' ')}
export function chooseCategories(title,summary,available,supplied=[]){
  const canonical=new Map(available.filter(n=>n.toLowerCase()!=='unsorted').map(name=>[name.toLowerCase(),name]));
  const chosen=(Array.isArray(supplied)?supplied:[]).filter(n=>typeof n==='string'&&n.trim()&&n.trim().toLowerCase()!=='unsorted').map(n=>canonical.get(n.trim().toLowerCase())||n.trim());
  if(chosen.length)return [...new Set(chosen)];
  const text=title+' '+summary,groups=[
    [/\b(dentist|dental|doctor|medical|health|prescription|pharmacy|therapy|checkup)\b/i,'Health',['health','medical','healthcare','wellness','personal']],
    [/\b(computer|software|server|laptop|network|printer|technical)\b/i,'Technology',['technology','it','tech','work']],
    [/\b(bill|tax|bank|budget|payment|finance)\b/i,'Finance',['finance','finances','money','personal']],
    [/\b(house|home|repair|laundry|clean|groceries|garden)\b/i,'Home',['home','household','errands','personal']],
    [/\b(project|report|briefing|team|client|work|meeting)\b/i,'Work',['work','projects','business']]
  ];
  for(const [pattern,fallback,aliases] of groups)if(pattern.test(text)){for(const alias of aliases)if(canonical.has(alias))return [canonical.get(alias)];return [fallback]}
  for(const [lower,name] of canonical)if(lower.length>3&&text.toLowerCase().includes(lower))return [name];
  return [canonical.get('personal')||'Personal'];
}

export function recurringIntent(text){return /\b(daily|weekly|monthly|quarterly|yearly|annually|every\s+(?:day|week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|repeat(?:ing)?)\b/i.test(text)}
