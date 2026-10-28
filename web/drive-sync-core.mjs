/* Transport-independent, multi-value register journal. No credentials or chat data. */
export const FIELDS = Object.freeze({
  task:['id','title','summary','state','categories','revisit_at','due_at','recurrence','next_occurrence','archived_at','created_at','updated_at'],
  entry:['id','thread_id','kind','body','done','due_at','revisit_at','created_at'],
  note:['id','action_id','body','created_at','updated_at'],
});
const clone=v=>structuredClone(v);
export const stable=v=>JSON.stringify(canonical(v));
function canonical(v){return Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v}
export class SyncError extends Error {constructor(message,status=422){super(message);this.status=status}}
const own=(object,key)=>Object.hasOwn(object,key);
const plain=value=>!!value&&typeof value==='object'&&!Array.isArray(value)&&(Object.getPrototypeOf(value)===null||Object.getPrototypeOf(Object.getPrototypeOf(value))===null);
const idPattern=/^[A-Za-z0-9_-]{1,128}$/;
const historyId=/^[A-Za-z0-9_-]{8,100}$/;
const nullableDates=new Set(['due_at','revisit_at','next_occurrence','archived_at']);
function validDate(value,nullable=false){
  if(value===null&&nullable)return true;
  if(typeof value!=='string'||value.length>64||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)||!Number.isFinite(Date.parse(value)))return false;
  const [year,month,day]=value.slice(0,10).split('-').map(Number);
  const days=[31,(year%4===0&&(year%100!==0||year%400===0))?29:28,31,30,31,30,31,31,30,31,30,31];
  const [hour,minute,second]=value.slice(11,19).split(':').map(Number);
  return year>=1&&month>=1&&month<=12&&day>=1&&day<=days[month-1]&&hour<24&&minute<60&&second<60;
}
function recordKey(key){
  if(typeof key!=='string')throw new SyncError('Invalid shared record ID');
  const [type,id,...rest]=key.split(':');
  if(rest.length||!own(FIELDS,type)||!idPattern.test(id||''))throw new SyncError('Invalid shared record ID');
  return [type,id];
}
function validateValue(type,field,value,id){
  const text=(max,required=false)=>typeof value==='string'&&value.length<=max&&(!required||!!value.trim());
  if(field==='$exists'){if(typeof value!=='boolean')throw new SyncError('Invalid deletion record');return}
  let valid=true;
  if(field==='id')valid=value===id;
  else if(field==='title')valid=text(300,true);
  else if(field==='summary')valid=text(20000);
  else if(field==='body')valid=text(20000,true);
  else if(field==='state')valid=['open','waiting','paused','settled'].includes(value);
  else if(field==='categories')valid=Array.isArray(value)&&value.length>=1&&value.length<=20&&value.every(v=>typeof v==='string'&&!!v.trim()&&v.length<=80)&&new Set(value.map(v=>v.toLowerCase())).size===value.length;
  else if(field==='recurrence')valid=[null,'daily','weekly','monthly','quarterly','yearly'].includes(value);
  else if(field==='kind')valid=['thought','question','action','decision','update'].includes(value);
  else if(field==='done')valid=[true,false,0,1].includes(value);
  else if(field==='thread_id'||field==='action_id')valid=typeof value==='string'&&idPattern.test(value);
  else if(field==='created_at'||field==='updated_at'||nullableDates.has(field))valid=validDate(value,nullableDates.has(field));
  else valid=false;
  if(!valid)throw new SyncError('Invalid shared '+field);
}
export function validateRecords(records){
  if(!plain(records)||Object.keys(records).length>10000)throw new SyncError('Invalid shared task records');
  let encoded;try{encoded=stable(records)}catch(_){throw new SyncError('Invalid shared task records')}
  if(new TextEncoder().encode(encoded).length>20*1024*1024)throw new SyncError('Shared Home data exceeds the 20 MB limit');
  for(const [key,row] of Object.entries(records)){
    const [type,id]=recordKey(key);
    if(!plain(row)||Object.keys(row).length!==FIELDS[type].length||FIELDS[type].some(field=>!own(row,field)))throw new SyncError('Private, unsupported or missing field in shared record');
    for(const [field,value] of Object.entries(row))validateValue(type,field,value,id);
    if(type==='entry'&&!own(records,'task:'+row.thread_id))throw new SyncError('Entry references a missing task');
    if(type==='note'&&(!own(records,'entry:'+row.action_id)||records['entry:'+row.action_id]?.kind!=='action'))throw new SyncError('Note references a missing action');
  }
  return records;
}
export function project(state){
  const records={};for(const [type,list] of [['task',state.tasks],['entry',state.entries],['note',state.notes]])for(const row of list||[]){
    const out={};for(const field of FIELDS[type]){
      if(row[field]!==undefined)out[field]=clone(row[field]);
      else if(nullableDates.has(field)||field==='recurrence')out[field]=null;
      else if(field==='summary')out[field]='';
      else if(field==='categories')out[field]=[row.category||'Unsorted'];
    }
    if(type==='entry')out.done=row.done?1:0;
    records[type+':'+row.id]=out;
  }return validateRecords(records);
}
export function applyToState(state,records){
  validateRecords(records);
  for(const [type,list] of [['task','tasks'],['entry','entries'],['note','notes']]){
    const old=new Map((state[list]||[]).map(row=>[row.id,row]));
    state[list]=Object.entries(records).filter(([key])=>key.startsWith(type+':')).map(([,row])=>{
      const previous=old.get(row.id)||{};
      const datesChanged=previous.revisit_at!==row.revisit_at,recurrenceChanged=previous.next_occurrence!==row.next_occurrence;
      return {...(type==='task'?{action_config:{},action_prompt:null,due_action:null,notified_for:null,recurring_notified_for:null}:type==='entry'?{notified_for:null}:{}),...previous,...clone(row),...(type==='task'?{category:row.categories[0]||'Unsorted'}:{}),...(type!=='note'&&datesChanged?{notified_for:null}:{}),...(type==='task'&&recurrenceChanged?{recurring_notified_for:null}:{})};
    });
  }
  const ids=new Set(state.tasks.map(t=>t.id));state.relations=(state.relations||[]).filter(r=>ids.has(r.a)&&ids.has(r.b));state.activity=(state.activity||[]).filter(r=>ids.has(r.thread_id));
}
function validOperation(op){
  if(!plain(op)||Object.keys(op).sort().join(',')!=='actor,changes,id,version,when'||op.version!==1||typeof op.id!=='string'||!historyId.test(op.id)||typeof op.actor!=='string'||!historyId.test(op.actor)||!validDate(op.when)||!Array.isArray(op.changes)||!op.changes.length||op.changes.length>50000)throw new SyncError('Invalid Drive change record');
  let encoded;try{encoded=stable(op)}catch(_){throw new SyncError('Invalid Drive change record')}
  if(new TextEncoder().encode(encoded).length>5_000_000)throw new SyncError('Drive change record is too large');
  const seen=new Set();for(const c of op.changes){
    if(!plain(c)||Object.keys(c).sort().join(',')!=='field,key,parents,value'||typeof c.field!=='string')throw new SyncError('Invalid change');
    const [type,id]=recordKey(c.key);
    if((!FIELDS[type].includes(c.field)&&c.field!=='$exists')||c.field==='updated_at'||!Array.isArray(c.parents)||c.parents.length>1000||new Set(c.parents).size!==c.parents.length||c.parents.some(p=>typeof p!=='string'||!historyId.test(p))||c.parents.includes(op.id))throw new SyncError('Invalid change field or history');
    validateValue(type,c.field,c.value,id);
    const token=c.key+'\0'+c.field;if(seen.has(token))throw new SyncError('Duplicate change field');seen.add(token);
  }
}
export function mergeJournal(...logs){
  const map=new Map();let totalChanges=0,totalBytes=0;for(const op of logs.flat()){
    validOperation(op);if(!map.has(op.id)){totalChanges+=op.changes.length;totalBytes+=stable(op).length;if(totalChanges>250000||totalBytes>50_000_000)throw new SyncError('Sync history needs maintenance; no local changes were discarded')}if(map.has(op.id)&&stable(map.get(op.id))!==stable(op))throw new SyncError('Conflicting copies of a Drive change record');map.set(op.id,clone(op));
    if(map.size>50000)throw new SyncError('Sync history needs maintenance; no local changes were discarded');
  }return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id));
}
export function registers(log){
  const all=new Map(),superseded=new Map(),parentsByToken=new Map();
  for(const op of mergeJournal(log))for(const change of op.changes){
    const token=change.key+'\0'+change.field;
    if(!all.has(token)){all.set(token,new Map());parentsByToken.set(token,new Map());superseded.set(token,new Set())}
    all.get(token).set(op.id,{id:op.id,actor:op.actor,when:op.when,value:clone(change.value)});
    parentsByToken.get(token).set(op.id,change.parents);
    for(const p of change.parents)superseded.get(token).add(p);
  }
  for(const [token,parents] of superseded){
    for(const p of parents)if(!all.get(token).has(p))throw new SyncError('Drive history is incomplete. Reconnect all shared journals before syncing.');
    // Kahn traversal catches cycles without recursion or silently dropping values.
    const graph=parentsByToken.get(token),remaining=new Map([...graph].map(([id,ps])=>[id,ps.length])),children=new Map();
    for(const [id,ps] of graph)for(const p of ps){if(!children.has(p))children.set(p,[]);children.get(p).push(id)}
    const ready=[...remaining].filter(([,count])=>count===0).map(([id])=>id);let visited=0;
    for(let index=0;index<ready.length;index++){const id=ready[index];visited++;for(const child of children.get(id)||[]){remaining.set(child,remaining.get(child)-1);if(remaining.get(child)===0)ready.push(child)}}
    if(visited!==graph.size)throw new SyncError('Drive history contains a cycle; no local data was changed');
  }
  return new Map([...all].map(([token,values])=>[token,[...values.values()].filter(v=>!superseded.get(token).has(v.id)).sort((a,b)=>a.id.localeCompare(b.id))]));
}
export function makeChanges(log,before,after,actor,id,when=new Date().toISOString()){
  validateRecords(before);validateRecords(after);const regs=registers(log),changes=[];
  for(const key of new Set([...Object.keys(before),...Object.keys(after)])){
    const comparable=row=>row&&Object.fromEntries(Object.entries(row).filter(([field])=>field!=='updated_at'));
    if(stable(comparable(before[key]))===stable(comparable(after[key])))continue;
    const write=(field,value)=>changes.push({key,field,value:clone(value),parents:(regs.get(key+'\0'+field)||[]).map(v=>v.id)});
    write('$exists',!!after[key]);if(!after[key])continue;
    for(const [field,value] of Object.entries(after[key]))if(field!=='updated_at'&&(before[key]===undefined||stable(before[key][field])!==stable(value)))write(field,value);
  }
  // Editing an owned child also observes its ancestors as alive, detecting delete/edit conflicts.
  for(const change of [...changes])if(after[change.key]){const row=after[change.key];const parents=change.key.startsWith('entry:')?['task:'+row.thread_id]:change.key.startsWith('note:')?['entry:'+row.action_id,'task:'+after['entry:'+row.action_id]?.thread_id]:[];for(const key of parents)if(after[key]&&!changes.some(c=>c.key===key&&c.field==='$exists'))changes.push({key,field:'$exists',value:true,parents:(regs.get(key+'\0$exists')||[]).map(v=>v.id)});}
  if(!changes.length)return null;const op={version:1,id,actor,when,changes};validOperation(op);return op;
}
export function materialize(log,preferred={}){
  const regs=registers(log),records={},conflicts=[],byRecord=new Map();
  for(const [token,values] of regs){const [key,field]=token.split('\0');if(!byRecord.has(key))byRecord.set(key,new Map());byRecord.get(key).set(field,values)}
  const pick=(token,values)=>{
    const unique=[...new Map(values.map(v=>[stable(v.value),v])).values()];
    if(unique.length>1)conflicts.push({key:token.split('\0')[0],field:token.split('\0')[1],choices:clone(values)});
    const key=token.split('\0')[0],field=token.split('\0')[1],wanted=field==='$exists'?!!preferred[key]:preferred[key]?.[field];
    const chosen=values.find(v=>stable(v.value)===stable(wanted));return chosen?chosen.value:values[0]?.value;
  };
  for(const [key,fields] of byRecord){const exists=fields.get('$exists');if(!exists)continue;
    if(pick(key+'\0$exists',exists)){records[key]={};for(const [field,values] of fields)if(field!=='$exists')records[key][field]=clone(pick(key+'\0'+field,values));}
  }
  // A deleted task owns its children: do not resurrect orphaned notes/actions.
  for(const [key,row] of Object.entries(records))if(key.startsWith('entry:')&&!records['task:'+row.thread_id])delete records[key];
  for(const [key,row] of Object.entries(records))if(key.startsWith('note:')&&!records['entry:'+row.action_id])delete records[key];
  for(const [key,row] of Object.entries(records))if(key.startsWith('task:')||key.startsWith('note:'))row.updated_at=[...byRecord.get(key).values()].flatMap(vs=>vs.map(v=>v.when)).sort((a,b)=>Date.parse(a)-Date.parse(b)||a.localeCompare(b)).at(-1)||row.created_at;
  validateRecords(records);return {records,conflicts};
}
export function resolve(log,key,field,value,actor,id){
  const heads=registers(log).get(key+'\0'+field);if(!heads?.length)throw new SyncError('Conflict no longer exists');
  if(!heads.some(h=>stable(h.value)===stable(value)))throw new SyncError('Choose one of the preserved values');
  const op={version:1,id,actor,when:new Date().toISOString(),changes:[{key,field,value:clone(value),parents:heads.map(h=>h.id)}]};validOperation(op);return op;
}
