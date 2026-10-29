/* Browser task engine. All writes are committed in a single IndexedDB transaction. */
import {calendarDate,recurrenceValue,recurrenceZone,scheduleDay,recurrenceDue,occurrenceDay,occurrences,nextOccurrence} from './recurrence.mjs';
import {requestLocation} from './locations.mjs';
import {briefNote} from './notes.mjs';
import {preferences,DEFAULT_PREFERENCES,resolveReminder,chooseCategories,taskKey} from './decisions.mjs';
export const SCHEMA = 1;
export const now = () => new Date().toISOString();
export const uid = () => crypto.randomUUID ? crypto.randomUUID().replaceAll('-', '')
  : Array.from(crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('');
export const copy = value => structuredClone(value);
const states = ['open', 'waiting', 'paused', 'settled'];
const kinds = ['thought', 'question', 'action', 'decision', 'update'];
const activities = ['progress', 'feedback', 'decision', 'blocker', 'milestone', 'other'];
const frequencies = ['daily', 'weekly', 'monthly', 'quarterly', 'yearly'];
const periods = ['week', 'month', 'quarter', 'year'];
export class Problem extends Error {
  constructor(message, status = 422) { super(message); this.status = status; }
}
export function required(value, label = 'Text', limit = 20000) {
  if (typeof value !== 'string' || !value.trim() || value.length > limit)
    throw new Problem(`${label} must contain 1–${limit} characters`);
  return value.trim();
}
export function timestamp(value) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\d(?:T.*(?:Z|[+-]\d\d:\d\d))?$/.test(value))
    throw new Problem('Use an ISO date or a date/time including its timezone');
  const date = new Date(value.length === 10 ? value + 'T12:00:00Z' : value);
  if (!Number.isFinite(date.getTime()) || value.length === 10 && date.toISOString().slice(0,10)!==value) throw new Problem('Invalid date');
  return date.toISOString();
}
export function categories(names) {
  if (!Array.isArray(names) || names.length > 20) throw new Problem('Use at most 20 categories');
  const seen = new Set(), result = [];
  for (const name of names) {
    const clean = required(name, 'Category', 80), key = clean.toLowerCase();
    if (!seen.has(key)) { result.push(clean); seen.add(key); }
  }
  const clean = result.length > 1 ? result.filter(n => n.toLowerCase() !== 'unsorted') : result;
  return clean.length ? clean : ['Unsorted'];
}
export function emptyState() {
  return {schema: SCHEMA, tasks: [], entries: [], notes: [], activity: [], relations: [],
    messages: [], jobs: [], settings: {}, preferences:{...DEFAULT_PREFERENCES}, assistant_context:{}, notificationClaims: {}};
}
export class Database {
  constructor(name) { this.name = name; }
  async open() {
    this.db = await new Promise((resolve, reject) => {
      const request = indexedDB.open(this.name, 1);
      request.onupgradeneeded = () => request.result.createObjectStore('state');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Problem('Close other tether tabs to finish updating storage'));
    });
    this.db.onversionchange = () => this.db.close();
    await this.write(state => {state.preferences=preferences(state.preferences||{});return null});
    return this;
  }
  read(fn) { return this.transaction(fn, 'readonly'); }
  write(fn) { return this.transaction(fn, 'readwrite'); }
  transaction(fn, mode) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction('state', mode), store = transaction.objectStore('state');
      const request = store.get('data'); let result, error;
      request.onsuccess = () => {
        try {
          const state = request.result || emptyState();
          if (state.schema !== SCHEMA) throw new Problem('This data needs a newer version of tether');
          result = fn(state);
          if (result && typeof result.then === 'function') throw new Error('Database callbacks must be synchronous');
          result = copy(result);
          if (mode === 'readwrite') store.put(state, 'data');
        } catch (exc) { error = exc; transaction.abort(); }
      };
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = () => reject(error || transaction.error);
      transaction.onabort = () => reject(error || transaction.error || new Problem('Storage write failed'));
    });
  }
}
export class Model {
  constructor(state, clock = now) { this.s = state; this.clock = clock; }
  preferences(){return preferences(this.s.preferences||{})}
  setPreferences(fields){try{this.s.preferences=preferences({...this.preferences(),...fields});return copy(this.s.preferences)}catch(error){throw new Problem(error.message)}}
  categoryNames(){return [...new Set(this.s.tasks.flatMap(t=>t.categories||[t.category||'Unsorted']))].filter(name=>name.toLowerCase()!=='unsorted').sort()}
  focus(id){
    if(id && this.s.tasks.some(t=>t.id===id))this.s.assistant_context={task_id:id};
    let task=this.s.tasks.find(t=>t.id===this.s.assistant_context?.task_id && !t.archived_at && t.state!=='settled');
    if(!task){for(const row of this.s.messages.filter(m=>m.role==='assistant').slice(-10).reverse()){
      const ids=[...new Set([...row.body.matchAll(/#task\/([A-Za-z0-9_-]+)/g)].map(match=>match[1]))];
      if(ids.length===1){task=this.s.tasks.find(t=>t.id===ids[0]&&!t.archived_at&&t.state!=='settled');if(task)break}
    }}
    const active=this.s.tasks.filter(t=>!t.archived_at&&t.state!=='settled');
    if(!task && active.length && new Set(active.map(t=>taskKey(t.title))).size===1)task=active[0];
    return task?this.get(task.id):null;
  }
  assistantContext(){const p=this.preferences(),focused=this.focus();return {preferences:p,available_categories:this.categoryNames(),focused_task:focused?{id:focused.id,title:focused.title,categories:focused.categories,summary:focused.summary.slice(0,300),revisit_at:focused.revisit_at,due_at:focused.due_at}:null,
    recent_tasks:this.list().filter(t=>!t.archived_at&&t.state!=='settled').slice(0,12).map(t=>({id:t.id,title:t.title,categories:t.categories,summary:t.summary.slice(0,200),revisit_at:t.revisit_at})),
    default_reminder_choices:Object.fromEntries(['tomorrow','next week','next month','next year'].map(period=>[period,resolveReminder(period,p,new Date(this.clock()))]))}}
  capture(args){
    const title=required(args.title,'Title',300),key=taskKey(title);
    let existing=args.existing_id?this.task(args.existing_id):this.s.tasks.find(t=>!t.archived_at&&t.state!=='settled'&&key&&taskKey(t.title)===key);
    const reused=!!existing;
    if(existing?.archived_at)throw new Problem('Restore this archived task before changing it');
    const names=chooseCategories(title,args.summary||'',this.categoryNames(),args.categories||[]);
    let reminder;try{if(args.remind_at)reminder=resolveReminder(args.remind_at,this.preferences(),new Date(this.clock()))}catch(error){throw new Problem(error.message)}
    if(existing){
      const fields={};if(existing.categories.every(name=>name.toLowerCase()==='unsorted'))fields.categories=names;
      if(args.summary&&!existing.summary)fields.summary=args.summary;
      if(reminder)fields.revisit_at=reminder;
      if(Object.keys(fields).length)this.update(existing.id,fields);
    }else{existing=this.create(title,args.summary||'',names);if(reminder)this.update(existing.id,{revisit_at:reminder})}
    this.focus(existing.id);return {...this.get(existing.id),reused};
  }
  task(id) {
    const task = this.s.tasks.find(t => t.id === id);
    if (!task) throw new Problem('Task not found', 404);
    return task;
  }
  action(id) {
    const entry = this.s.entries.find(e => e.id === id && e.kind === 'action');
    if (!entry) throw new Problem('Action item not found', 404);
    return entry;
  }
  touch(id) { this.task(id).updated_at = this.clock(); }
  get(id) {
    const t = this.task(id);
    return {...t, entries: this.s.entries.filter(e => e.thread_id === id).map(e =>
      e.kind === 'action' ? {...e, notes: this.notes(e.id)} : {...e}),
    activity: this.s.activity.filter(e => e.thread_id === id).sort((a,b) => b.occurred_at.localeCompare(a.occurred_at)),
    related: this.s.relations.filter(r => r.a === id || r.b === id).map(r => {
      const other = this.task(r.a === id ? r.b : r.a); return {id: other.id, title: other.title};
    })};
  }
  list(query = '') {
    const q = String(query).toLowerCase(), stamp = this.clock();
    return this.s.tasks.filter(t => {
      const entries = this.s.entries.filter(e => e.thread_id === t.id);
      return [t.title, t.summary, ...t.categories, ...entries.map(e => e.body),
        ...this.s.notes.filter(n => entries.some(e => e.id === n.action_id)).map(n => n.body)]
        .some(value => String(value).toLowerCase().includes(q));
    }).map(t => {
      const active = t.state !== 'settled' && !t.archived_at;
      const attention_due = !!(active && t.revisit_at && recurrenceDue({next_occurrence:t.revisit_at},stamp));
      const recurring_due = !!(active && t.recurrence && t.next_occurrence && recurrenceDue(t,stamp));
      return {...t, entry_count: this.s.entries.filter(e => e.thread_id === t.id).length,
        attention_due, recurring_due, due: attention_due || (recurring_due && !t.revisit_at),
        deadline_due: !!(active && t.due_at && occurrenceDay(t.due_at) <= occurrenceDay(stamp))};
    }).sort((a,b) => Number(b.due) - Number(a.due) || b.updated_at.localeCompare(a.updated_at));
  }
  create(title, summary = '', names = []) {
    title = required(title, 'Title', 300);
    if (typeof summary !== 'string') throw new Problem('Details must be text');
    const cats = categories(names), stamp = this.clock(), id = uid();
    this.s.tasks.push({id, title, summary, state: 'open', categories: cats, category: cats[0],
      revisit_at: null, due_at: null, recurrence: null, next_occurrence: null, recurrence_end:null, recurrence_anchor:null, recurrence_timezone:null, due_action: null,
      action_config: {}, action_prompt: null, archived_at: null, notified_for: null,
      recurring_notified_for: null, created_at: stamp, updated_at: stamp});
    return this.get(id);
  }
  update(id, fields) {
    const task = this.task(id), changes = {};
    for (const [key, value] of Object.entries(fields)) {
      if (key === 'title') changes.title = required(value, 'Title', 300);
      else if (key === 'summary' || key === 'action_prompt') {
        if (value !== null && (typeof value !== 'string' || (key === 'action_prompt' && value.length > 1000)))
          throw new Problem('Invalid task details');
        changes[key] = value || '';
      } else if (key === 'state') {
        if (!states.includes(value)) throw new Problem('Invalid task state'); changes.state = value;
      } else if (['next_occurrence','recurrence_anchor'].includes(key)) {try{changes[key]=recurrenceValue(value)}catch(error){throw new Problem(error.message)}}
      else if(key==='recurrence_end'){try{changes[key]=value===null?null:calendarDate(value)}catch(error){throw new Problem(error.message)}}
      else if(key==='recurrence_timezone'){try{changes[key]=recurrenceZone(value)}catch(error){throw new Problem(error.message)}}
      else if (['due_at', 'revisit_at', 'archived_at'].includes(key)) changes[key] = key==='due_at'&&typeof value==='string'&&value.length===10?calendarDate(value):timestamp(value);
      else if (key === 'recurrence') {
        if (value !== null && !frequencies.includes(value)) throw new Problem('Invalid recurrence'); changes[key] = value;
      } else if (key === 'due_action') {
        if (value !== null && value !== 'activity_report') throw new Problem('Invalid due action'); changes[key] = value;
      } else if (key === 'action_config') {
        if (!value || Array.isArray(value) || typeof value !== 'object' ||
            Object.keys(value).some(k => !['period','category'].includes(k)) ||
            !periods.includes(value.period || 'week') ||
            (value.category !== undefined && (typeof value.category !== 'string' || value.category.length > 80)))
          throw new Problem('Invalid report configuration');
        changes[key] = copy(value);
      }
    }
    if ('categories' in fields || 'category' in fields) {
      changes.categories = categories(fields.categories ?? [fields.category]); changes.category = changes.categories[0];
    }
    if ('revisit_at' in changes) changes.notified_for = null;
    const sameOccurrence=(a,b)=>a===b||!!a&&!!b&&(a.length===10)===(b.length===10)&&Date.parse(a)===Date.parse(b);
    const scheduleChanged=['recurrence','next_occurrence','recurrence_timezone'].some(key=>key in changes&&(key==='next_occurrence'?!sameOccurrence(changes[key],task[key]):changes[key]!==task[key]));
    if(scheduleChanged&&!('recurrence_anchor' in changes))changes.recurrence_anchor=changes.next_occurrence===undefined?task.next_occurrence:changes.next_occurrence;
    if('next_occurrence' in changes)changes.recurring_notified_for=null;
    if('recurrence' in changes&&!changes.recurrence)Object.assign(changes,{next_occurrence:null,recurrence_anchor:null,recurrence_end:null,recurrence_timezone:null});
    const updated={...task,...changes};if(updated.recurrence_end&&updated.next_occurrence&&updated.recurrence_end<scheduleDay(updated.next_occurrence,updated.recurrence_timezone))throw new Problem('Repeat end cannot be before the next occurrence');
    Object.assign(task, changes, {updated_at: this.clock()}); return this.get(id);
  }
  setCategories(id, names, mode = 'replace') {
    const task = this.task(id), incoming = names.length ? categories(names) : [];
    if (!['add','remove','replace'].includes(mode)) throw new Problem('Invalid category mode');
    const result = mode === 'add' ? [...task.categories, ...incoming] : mode === 'remove'
      ? task.categories.filter(n => !incoming.some(v => v.toLowerCase() === n.toLowerCase())) : incoming;
    return this.update(id, {categories: categories(result)});
  }
  add(id, kind, body) {
    this.task(id);
    if (!kinds.includes(kind)) throw new Problem('Invalid entry type');
    const entry = {id: uid(), thread_id: id, kind, body: required(body, 'Entry'), done: false,
      due_at: null, revisit_at: null, notified_for: null, created_at: this.clock()};
    this.s.entries.push(entry); this.touch(id); return entry;
  }
  updateAction(id, fields) {
    const action = this.action(id), changes = {};
    if ('done' in fields) {
      if (typeof fields.done !== 'boolean') throw new Problem('Completion must be true or false'); changes.done = fields.done;
    }
    for (const key of ['due_at','revisit_at']) if (key in fields) changes[key] = key==='due_at'&&typeof fields[key]==='string'&&fields[key].length===10?calendarDate(fields[key]):timestamp(fields[key]);
    if ('revisit_at' in changes) changes.notified_for = null;
    Object.assign(action, changes); this.touch(action.thread_id); return action;
  }
  notes(id) { this.action(id); return this.s.notes.filter(n => n.action_id === id); }
  addNote(id, body, noteId = uid()) {
    const action = this.action(id); body = required(body, 'Note'); required(noteId, 'Note ID', 100);
    const previous = this.s.notes.find(n => n.id === noteId);
    if (previous) {
      if (previous.action_id !== id || previous.body !== body) throw new Problem('This note ID is already in use');
      return previous;
    }
    const stamp = this.clock(), note = {id: noteId, action_id: id, body, created_at: stamp, updated_at: stamp};
    this.s.notes.push(note); this.touch(action.thread_id); return note;
  }
  editNote(id, noteId, body) {
    const action = this.action(id), note = this.notes(id).find(n => n.id === noteId);
    if (!note) throw new Problem('Note not found under this action', 404);
    note.body = required(body, 'Note'); note.updated_at = this.clock(); this.touch(action.thread_id); return note;
  }
  deleteNote(id, noteId) {
    const action = this.action(id), index = this.s.notes.findIndex(n => n.action_id === id && n.id === noteId);
    if (index < 0) throw new Problem('Note not found under this action', 404);
    this.s.notes.splice(index, 1); this.touch(action.thread_id); return {deleted: true};
  }
  remove(id) {
    this.task(id); const ids = new Set(this.s.entries.filter(e => e.thread_id === id).map(e => e.id));
    this.s.tasks = this.s.tasks.filter(t => t.id !== id); this.s.entries = this.s.entries.filter(e => e.thread_id !== id);
    this.s.notes = this.s.notes.filter(n => !ids.has(n.action_id)); this.s.activity = this.s.activity.filter(e => e.thread_id !== id);
    this.s.relations = this.s.relations.filter(r => r.a !== id && r.b !== id); return {deleted: true};
  }
  link(a, b) {
    this.task(a); this.task(b); if (a === b) throw new Problem('Choose two different tasks');
    [a,b] = [a,b].sort(); if (!this.s.relations.some(r => r.a === a && r.b === b)) this.s.relations.push({a,b});
    return {linked: true};
  }
  board() {
    const groups = new Map();
    for (const t of this.list().filter(t => !t.archived_at)) for (const name of t.categories) {
      if (!groups.has(name)) groups.set(name, []); groups.get(name).push(t);
    }
    return [...groups].sort(([a],[b]) => Number(a === 'Unsorted') - Number(b === 'Unsorted') || a.localeCompare(b))
      .map(([name,threads]) => ({name,threads}));
  }
  overview() {
    const rows = this.list().filter(t => !t.archived_at);
    return {deadlines: rows.filter(t => t.deadline_due), due: rows.filter(t => t.due),
      active: rows.filter(t => t.state === 'open' && !t.due), waiting: rows.filter(t => t.state === 'waiting'),
      paused: rows.filter(t => t.state === 'paused'), settled: rows.filter(t => t.state === 'settled')};
  }
  brief() {
    return briefNote(this.overview(),id=>this.get(id));
  }
  record(id, body, kind = 'progress', occurredAt = null) {
    this.task(id); if (!activities.includes(kind)) throw new Problem('Invalid activity type');
    const event = {id: uid(), thread_id: id, kind, body: required(body, 'Activity', 10000),
      occurred_at: timestamp(occurredAt) || this.clock(), recorded_at: this.clock()};
    this.s.activity.push(event); this.touch(id); return event;
  }
  report(period = 'week', anchor = null) {
    if (!periods.includes(period)) throw new Problem('Invalid reporting period');
    const ref = new Date(timestamp(anchor) || this.clock()); let start, end;
    if (period === 'week') {
      start = new Date(Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate() - (ref.getUTCDay()+6)%7));
      end = new Date(+start + 7*86400000);
    } else {
      const month = period === 'year' ? 0 : period === 'quarter' ? Math.floor(ref.getUTCMonth()/3)*3 : ref.getUTCMonth();
      start = new Date(Date.UTC(ref.getUTCFullYear(), month, 1));
      end = new Date(Date.UTC(ref.getUTCFullYear(), month + ({month:1,quarter:3,year:12}[period]), 1));
    }
    const events = this.s.activity.filter(e => e.occurred_at >= start.toISOString() && e.occurred_at < end.toISOString())
      .sort((a,b) => b.occurred_at.localeCompare(a.occurred_at)).map(e => {
        const t = this.task(e.thread_id); return {...e, title:t.title, category:t.category, categories:t.categories};
      });
    return {period, start:start.toISOString(), end:end.toISOString(), events, count:events.length};
  }
  dueReport(id, anchor = null) {
    const task = this.task(id); if (task.due_action !== 'activity_report') throw new Problem('No activity report configured');
    const config = task.action_config, ref = new Date(timestamp(anchor) || this.clock());
    const report = this.report(config.period || 'week', new Date(+ref - 1).toISOString());
    if (config.category) report.events = report.events.filter(e => e.categories.includes(config.category));
    return {...report, count:report.events.length, category:config.category || null, thread_id:id};
  }
  complete(id, description = 'Completed recurring occurrence', occurrenceAt = null) {
    const task = this.task(id), stamp=this.clock(), original=task.next_occurrence;
    if (!task.recurrence) throw new Problem('This task does not have a recurring date');
    const same=(a,b)=>a===b||!!a&&!!b&&(a.length===10)===(b.length===10)&&Date.parse(a)===Date.parse(b);
    const reason=occurrenceAt!==null&&!same(occurrenceAt,original)?'occurrence_changed':!original?'no_remaining_occurrence':task.state==='settled'||task.archived_at?'inactive':occurrenceAt===null&&!recurrenceDue(task,stamp)?'not_due':null;
    if(reason)return {...this.get(id),completion:{completed:false,occurrence_at:occurrenceAt,reason}};
    description=required(description,'Completion description',10000);
    let next;try{next=nextOccurrence(task,stamp)}catch(error){throw new Problem(error.message)}
    this.update(id, {next_occurrence: next,recurrence_anchor:task.recurrence_anchor||original}); this.record(id, description, 'milestone');
    return {...this.get(id),completion:{completed:true,occurrence_at:original,next_occurrence:next}};
  }
  attention() {
    const active = this.list().filter(t => !t.archived_at && t.state !== 'settled'), lookup = new Map(active.map(t => [t.id,t]));
    const due = value => !!(value && recurrenceDue({next_occurrence:value}, this.clock())), items = [];
    for (const a of this.s.entries.filter(e => e.kind === 'action' && !e.done)) {
      const task = lookup.get(a.thread_id);
      if (task && (due(a.revisit_at) || due(a.due_at))) items.push({id:a.id, task_id:task.id, action_id:a.id,
        title:a.body, task_title:task.title, reason:due(a.revisit_at) ? 'Scheduled attention' : 'Action due'});
    }
    for (const t of active.filter(t => t.due || t.deadline_due)) items.push({id:t.id,task_id:t.id,action_id:null,title:t.title,reason:t.attention_due?'Scheduled attention':t.deadline_due?'Task due':'Recurring occurrence'});
    return {items:items.slice(0,20), source:'scheduled'};
  }
  snapshot(start, end, category = '') {
    const first = day(start), last = day(end), difference = (+last - +first)/86400000;
    if (difference < 0 || difference > 365) throw new Problem('Date range must be ordered and at most 366 days');
    const tasks = this.list().filter(t => !t.archived_at && (!category || t.categories.includes(category)));
    const events = this.s.activity.map(e => ({...e, ...Object.fromEntries(['title','category','categories'].map(k => [k,this.task(e.thread_id)[k]]))}))
      .filter(e => (!category || e.categories.includes(category)) && e.occurred_at.slice(0,10) >= start && e.occurred_at.slice(0,10) <= end);
    const days = [], categoryCounts = {}, activityTypes = {};
    const localDay=value=>{if(!value)return null;if(/^\d{4}-\d\d-\d\d$/.test(value))return value;const d=new Date(value);if(!Number.isFinite(+d))return null;return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-')};
    const scheduled=[];
    const add=(task,action=null)=>{
      const record=action||task,dates=new Map();
      for(const [field,kind] of [['due_at','deadline'],['revisit_at','reminder'],...(!action&&!task.recurrence?[['next_occurrence','reminder']]:[])]){
        const date=localDay(record[field]);if(!date||date<start||date>end)continue;
        if(!dates.has(date))dates.set(date,new Set());dates.get(date).add(kind);
      }
      const projected=new Map();if(!action)for(const item of occurrences(task,start,end)){projected.set(item.date,item.value);if(!dates.has(item.date))dates.set(item.date,new Set());dates.get(item.date).add('recurrence')}
      for(const [date,kinds] of dates)scheduled.push({id:task.id,task_id:task.id,action_id:action?.id||null,title:action?.body||task.title,task_title:task.title,
        category:task.category,categories:task.categories,state:action?.done?'settled':task.state,date,schedule_kinds:[...kinds],
        summary:(task.summary||'').slice(0,300),location:(this.s.location_requests||[]).filter(r=>r.task_id===task.id&&r.status==='saved'&&r.selected?.address).at(-1)?.selected.address||'',
        note_preview:(action?this.notes(action.id).at(-1)?.body:this.s.entries.filter(e=>e.thread_id===task.id&&e.kind!=='action').at(-1)?.body)?.slice(0,240)||'',
        due_at:record.due_at||null,revisit_at:record.revisit_at||null,next_occurrence:action?null:projected.get(date)||task.next_occurrence||null,occurrence_at:projected.get(date)||null,is_projection:!!projected.get(date)&&Date.parse(projected.get(date))!==Date.parse(task.next_occurrence),recurrence:action?null:task.recurrence||null,recurrence_end:action?null:task.recurrence_end||null,
        schedule_label:[kinds.has('deadline')?'Due':'',kinds.has('reminder')?'Reminder':'',kinds.has('recurrence')?'Repeats':'',action?.done?'Done':''].filter(Boolean).join(' · '),
        href:action?'/board#action/'+task.id+'/'+action.id:'/board#task/'+task.id});
    };
    for(const task of tasks){add(task);for(const action of this.s.entries.filter(e=>e.thread_id===task.id&&e.kind==='action'))add(task,action)}
    for (let date = +first; date <= +last; date += 86400000) {
      const iso = new Date(date).toISOString().slice(0,10);
      const due = scheduled.filter(t=>t.date===iso);
      due.sort((a,b) => a.category.localeCompare(b.category) || a.title.localeCompare(b.title));
      for (const task of due) for (const name of task.categories) categoryCounts[name] = (categoryCounts[name] || 0) + 1;
      days.push({date:iso,tasks:due,activity:events.filter(e => e.occurred_at.slice(0,10) === iso)});
    }
    for (const event of events) activityTypes[event.kind] = (activityTypes[event.kind] || 0) + 1;
    return {start,end,category:category || null,week_start:this.preferences().week_start,days,insights:{scheduled_due:days.reduce((n,d) => n+d.tasks.length,0),
      activity_events:events.length,active_days:days.filter(d => d.activity.length).length,categories:categoryCounts,activity_types:activityTypes},
    notice:'Task and action reminders and deadlines use local calendar dates. Activity uses recorded UTC dates. No historical changes are inferred.'};
  }
  dispatch(name, args) {
    switch (name) {
      case 'list_threads': return this.list(args.query || '').slice(0,100);
      case 'get_thread': return this.get(args.id);
      case 'overview': return this.overview();
      case 'capture': return this.capture(args);
      case 'request_location_lookup': return requestLocation(this,args);
      case 'get_preferences': return this.preferences();
      case 'set_preferences': return this.setPreferences(args);
      case 'list_categories': return this.categoryNames();
      case 'get_context': return this.assistantContext();
      case 'add_note': return this.add(args.id, args.kind || 'thought', args.text);
      case 'add_action_note': return this.addNote(args.action_id, args.text);
      case 'update_action_note': return this.editNote(args.action_id, args.note_id, args.text);
      case 'delete_action_note': return this.deleteNote(args.action_id, args.note_id);
      case 'update_action': {const fields={...args};if(fields.revisit_at)try{fields.revisit_at=resolveReminder(fields.revisit_at,this.preferences(),new Date(this.clock()))}catch(error){throw new Problem(error.message)}return this.updateAction(args.action_id, fields)}
      case 'set_status': return this.update(args.id, {state:args.state});
      case 'set_revisit': {let date;try{date=resolveReminder(args.when,this.preferences(),new Date(this.clock()))}catch(error){throw new Problem(error.message)}return this.update(args.id, {revisit_at:date})}
      case 'set_due_date': return this.update(args.id, {due_at:args.when});
      case 'set_category': return this.update(args.id, {categories:[args.category]});
      case 'set_categories': return this.setCategories(args.id, args.categories, args.mode || 'replace');
      case 'set_recurrence': {
        if(args.attention_mode!==undefined&&args.attention_mode!==null&&!['occurrence','independent'].includes(args.attention_mode))throw new Problem('Invalid recurrence attention mode');
        if(args.attention_mode==='occurrence'&&(!args.frequency||!args.next_occurrence))throw new Problem('Occurrence attention requires a recurring schedule');
        return this.update(args.id, {recurrence:args.frequency || null,next_occurrence:args.next_occurrence || null,...Object.fromEntries(['recurrence_end','recurrence_timezone'].filter(key=>key in args).map(key=>[key,args[key]])),...(args.attention_mode==='occurrence'?{revisit_at:null}:{})});
      }
      case 'complete_occurrence': return this.complete(args.id,args.description,args.occurrence_at);
      case 'recurring_items': return {due:this.list().filter(t => t.recurring_due),all:this.list().filter(t => t.recurrence && !t.archived_at)};
      case 'archive_thread': return this.update(args.id, {archived_at:args.archive === false ? null : this.clock()});
      case 'list_archived': return this.list(args.query || '').filter(t => t.archived_at);
      case 'daily_brief': return {brief:this.brief()};
      case 'log_activity': return this.record(args.id,args.text,args.kind,args.occurred_at);
      case 'activity_report': return this.report(args.period,args.anchor);
      case 'run_task_due_action': return this.dueReport(args.id,args.anchor);
      case 'set_task_due_action': return this.update(args.id, {due_action:args.action === 'none' ? null : args.action,
        action_config:args.action === 'none' ? {} : {period:args.period || 'week',category:args.category || ''}});
      case 'connect': return this.link(args.first,args.second);
      default: throw new Problem('Unknown tool');
    }
  }
}
export function advance(value, frequency) {
  const date = new Date(timestamp(value));
  if (frequency === 'daily' || frequency === 'weekly') return new Date(+date + (frequency === 'daily' ? 1 : 7)*86400000).toISOString();
  const months = {monthly:1,quarterly:3,yearly:12}[frequency]; if (!months) throw new Problem('Invalid recurrence');
  const originalDay = date.getUTCDate(); date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth()+months);
  const max = new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
  date.setUTCDate(Math.min(max,originalDay)); return date.toISOString();
}
export function day(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\d$/.test(value)) throw new Problem('Use dates in YYYY-MM-DD format');
  const date = new Date(value+'T00:00:00Z');
  if (!Number.isFinite(+date) || date.toISOString().slice(0,10) !== value) throw new Problem('Invalid calendar date');
  return date;
}
export function snapshotRange(text, today = new Date(),weekStart=1) {
  text = text.trim().toLowerCase();
  text = text.replace(/^\/snapshot\s+(week|month)$/, '/snapshot this $1').replace(/^\/snapshot\s+day$/, '/snapshot today');
  if (!/\bsnapshots?\b|\bcalendar (report|view|summary)\b|\bvisual (task |activity )?(report|summary)\b/.test(text)) return null;
  const localDay = [today.getFullYear(),String(today.getMonth()+1).padStart(2,'0'),String(today.getDate()).padStart(2,'0')].join('-');
  const date = day(localDay); let start, end, match;
  const shift = (d,n) => new Date(+d+n*86400000), iso = d => d.toISOString().slice(0,10);
  if ((match = text.match(/(\d{4}-\d\d-\d\d)\s+(?:to|through|until|–|—)\s+(\d{4}-\d\d-\d\d)/))) [start,end] = [day(match[1]),day(match[2])];
  else if (/\b(yesterday|tomorrow|today)\b/.test(text)) start = end = shift(date,text.includes('yesterday') ? -1 : text.includes('tomorrow') ? 1 : 0);
  else if ((match = text.match(/\b(last|previous|this|current|next)\s+(week|month)\b/))) {
    const offset = {last:-1,previous:-1,this:0,current:0,next:1}[match[1]];
    if (match[2] === 'week') { start=shift(date,-(date.getUTCDay()-weekStart+7)%7+offset*7); end=shift(start,6); }
    else { start=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+offset,1)); end=new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth()+1,0)); }
  } else if ((match = text.match(/\b(next|past|last)\s+(\d{1,3})\s+(days?|weeks?)\b/))) {
    const count = Number(match[2])*(match[3].startsWith('week') ? 7 : 1);
    if (count < 1 || count > 366) throw new Problem('Snapshots support 1–366 days');
    start=match[1] === 'next' ? date : shift(date,1-count); end=match[1] === 'next' ? shift(date,count-1) : date;
  } else if ((match = text.match(/\b\d{4}-\d\d-\d\d\b/))) start=end=day(match[0]);
  else { start=shift(date,-(date.getUTCDay()-weekStart+7)%7); end=shift(start,6); }
  if (+end < +start || +end - +start > 365*86400000) throw new Problem('Snapshot range must be 1–366 days');
  return [iso(start),iso(end)];
}
