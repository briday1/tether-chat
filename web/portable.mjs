import {emptyState, Model, Problem, categories, required, timestamp, copy} from './store.mjs';
import {preferences,DEFAULT_PREFERENCES} from './decisions.mjs';

const tables = ['tasks','entries','notes','activity','relations','messages'];
export function exportData(state) {
  return {format:'tether-chat', version:1, exported_at:new Date().toISOString(),
    data:{...Object.fromEntries(tables.map(name => [name, copy(state[name])])),preferences:preferences(state.preferences||{})}};
}
export function validateBackup(payload) {
  if (!payload || payload.format !== 'tether-chat' || payload.version !== 1 || !payload.data)
    throw new Problem('Choose a tether portable JSON backup');
  const state = emptyState(), data = payload.data;
  try{state.preferences=preferences(data.preferences||{})}catch(error){throw new Problem(error.message)}
  for (const name of tables) {
    if (!Array.isArray(data[name]) || data[name].length > 200000) throw new Problem('Invalid or oversized backup table: '+name);
  }
  const ids = new Set();
  function identifier(value) {
    required(value,'Record ID',100); if (ids.has(value)) throw new Problem('Duplicate backup record ID'); ids.add(value); return value;
  }
  for (const source of data.tasks) {
    const id = identifier(source.id), model = new Model(state);
    const task = model.create(required(source.title,'Title',300),source.summary || '',categories(source.categories || [source.category || 'Unsorted']));
    const saved = state.tasks.at(-1); saved.id = id;
    const fields = Object.fromEntries(['state','due_at','revisit_at','recurrence','next_occurrence','due_action','action_config','action_prompt','archived_at']
      .filter(key => source[key] !== undefined).map(key => [key,source[key]]));
    model.update(id,fields);
    saved.created_at = timestamp(source.created_at) || task.created_at;
    saved.updated_at = timestamp(source.updated_at) || saved.created_at;
  }
  for (const source of data.entries) {
    const model = new Model(state); model.task(source.thread_id);
    const entry = model.add(source.thread_id,source.kind,source.body);
    entry.id = identifier(source.id); entry.created_at = timestamp(source.created_at) || entry.created_at;
    if (entry.kind === 'action') model.updateAction(entry.id,{done:!!source.done,due_at:source.due_at || null,revisit_at:source.revisit_at || null});
  }
  for (const source of data.notes) {
    const note = new Model(state).addNote(source.action_id,source.body,identifier(source.id));
    note.created_at=timestamp(source.created_at) || note.created_at; note.updated_at=timestamp(source.updated_at) || note.created_at;
  }
  for (const source of data.activity) {
    const event = new Model(state).record(source.thread_id,source.body,source.kind,source.occurred_at);
    event.id=identifier(source.id); event.recorded_at=timestamp(source.recorded_at) || event.recorded_at;
  }
  for (const source of data.relations) new Model(state).link(source.a,source.b);
  for (const source of data.messages) {
    if (!['user','assistant'].includes(source.role) || typeof source.body !== 'string') throw new Problem('Invalid conversation record');
    state.messages.push({id:identifier(source.id),role:source.role,body:source.body,created_at:timestamp(source.created_at) || new Date().toISOString()});
  }
  // Restoring dependent rows must not change the original task modification dates.
  for (const task of state.tasks) task.updated_at=timestamp(data.tasks.find(t => t.id===task.id).updated_at) || task.updated_at;
  return state;
}
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k,canonical(value[k])]));
  return value;
}
export function importData(state, payload) {
  const incoming = validateBackup(payload), candidate = copy(state), counts = {};
  for (const table of tables) {
    const key = row => table === 'relations' ? row.a+'|'+row.b : row.id;
    const existing = new Map(candidate[table].map(row => [key(row),row])); counts[table]=0;
    for (const row of incoming[table]) {
      const before=existing.get(key(row));
      if (before) {
        // Notification delivery is device-specific; it is never a merge conflict.
        const clean = item => Object.fromEntries(Object.entries(item).filter(([k]) => !['notified_for','recurring_notified_for'].includes(k)));
        if (JSON.stringify(canonical(clean(before))) !== JSON.stringify(canonical(clean(row))))
          throw new Problem('This backup has a different version of an existing record. Import into an empty browser profile to retain both versions. Nothing was changed.');
      } else { candidate[table].push(row); counts[table]++; }
    }
  }
  // Validate cross-table references before committing any merged data.
  validateBackup(exportData(candidate));
  for (const table of tables) state[table]=candidate[table];
  if(payload.data.preferences && JSON.stringify(preferences(state.preferences||{}))===JSON.stringify(DEFAULT_PREFERENCES))state.preferences=incoming.preferences;
  return {ok:true,added:counts};
}
