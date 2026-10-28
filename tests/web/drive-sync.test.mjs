import test from 'node:test';import assert from 'node:assert/strict';
import {makeChanges,mergeJournal,materialize,resolve,project,applyToState,validateRecords,registers} from '../../tether/drive-sync-core.mjs';
const when='2026-10-28T00:00:00.000Z',actor='device_12345';
const task={id:'task1',title:'Milk',summary:'',state:'open',categories:['Groceries'],revisit_at:null,due_at:null,recurrence:null,next_occurrence:null,archived_at:null,created_at:when,updated_at:when};
const initial={'task:task1':task};const start=makeChanges([],{},initial,actor,'operation_0001',when);
test('separate fields merge; duplicates/reordered delivery converge',()=>{const a=structuredClone(initial),b=structuredClone(initial);a['task:task1'].title='Bread';b['task:task1'].summary='Wholegrain';const x=makeChanges([start],initial,a,actor,'operation_0002'),y=makeChanges([start],initial,b,'device_99999','operation_0003');const journal=mergeJournal([y,start],[x,start]);const out=materialize(journal);assert.equal(out.records['task:task1'].title,'Bread');assert.equal(out.records['task:task1'].summary,'Wholegrain');assert.equal(out.conflicts.length,0);assert.deepEqual(materialize(mergeJournal([x,y,start])),out)});
test('concurrent same field preserved until resolution',()=>{const a=structuredClone(initial),b=structuredClone(initial);a['task:task1'].title='Bread';b['task:task1'].title='Eggs';const log=[start,makeChanges([start],initial,a,actor,'operation_0002'),makeChanges([start],initial,b,'device_99999','operation_0003')];const out=materialize(log,a);assert.equal(out.records['task:task1'].title,'Bread');assert.equal(out.conflicts.length,1);const fixed=resolve(log,'task:task1','title','Eggs',actor,'operation_0004');assert.equal(materialize([...log,fixed]).conflicts.length,0);assert.equal(materialize([...log,fixed]).records['task:task1'].title,'Eggs')});
test('delete/edit conflict preserves task; settled deletion never resurrected by replay',()=>{const a=structuredClone(initial);a['task:task1'].title='Bread';const del=makeChanges([start],initial,{},actor,'operation_0002'),edit=makeChanges([start],initial,a,'device_99999','operation_0003');const log=[start,del,edit];assert.ok(materialize(log,a).conflicts.some(c=>c.field==='$exists'));const fix=resolve(log,'task:task1','$exists',false,actor,'operation_0004');assert.deepEqual(materialize(mergeJournal([...log,fix],[start,edit])).records,{})});
test('private fields never projected; notifications remain local',()=>{const state={tasks:[{...task,action_prompt:'secret',action_config:{},notified_for:'private'}],entries:[],notes:[],messages:[{body:'private'}],settings:{api_key:'secret'}};assert.equal(JSON.stringify(project(state)).includes('private'),false);const rows=structuredClone(initial);rows['task:task1'].title='Bread';applyToState(state,rows);assert.equal(state.tasks[0].action_prompt,'secret');assert.equal(state.settings.api_key,'secret');assert.equal(state.messages[0].body,'private')});
test('missing causal history, colliding IDs and injected private fields rejected',()=>{const a=structuredClone(initial);a['task:task1'].title='Bread';const op=makeChanges([start],initial,a,actor,'operation_0002');assert.throws(()=>materialize([op]),/incomplete/);assert.throws(()=>mergeJournal([start,{...start,when:'2027-01-01T00:00:00Z'}]),/Conflicting/);assert.throws(()=>makeChanges([],{}, {'task:task1':{...task,api_key:'bad'}},actor,'operation_0003'),/Private/)});
test('timestamp-only changes do not create sync loops',()=>{const a=structuredClone(initial);a['task:task1'].updated_at='2027-01-01T00:00:00Z';assert.equal(makeChanges([start],initial,a,actor,'operation_0002'),null)});

test('complete schema and timezone-aware dates are required',()=>{
  for(const mutate of [row=>delete row.revisit_at,row=>row.categories=[],row=>row.categories=['A','a'],row=>row.created_at=null,row=>row.created_at='2026-01-01',row=>row.due_at='2026-02-30T00:00:00Z',row=>row.updated_at='2026-01-01T00:00:00']){
    const records=structuredClone(initial);mutate(records['task:task1']);assert.throws(()=>validateRecords(records));
  }
});
test('browser projection fills nullable fields and canonical completion',()=>{
  const entry={id:'entry1',thread_id:'task1',kind:'action',body:'Get bread',created_at:when};
  const records=project({tasks:[task],entries:[entry]});
  assert.equal(records['entry:entry1'].done,0);assert.equal(records['entry:entry1'].due_at,null);assert.equal(records['entry:entry1'].revisit_at,null);
  assert.deepEqual(Object.keys(records['entry:entry1']).sort(),['id','thread_id','kind','body','done','due_at','revisit_at','created_at'].sort());
});
test('malicious types, prototype fields and values fail closed',()=>{
  const prototype=JSON.parse('{"__proto__:evil":{"id":"evil"}}');assert.throws(()=>validateRecords(prototype));
  for(const bad of [
    {...start,changes:[{key:'constructor:evil',field:'id',value:'evil',parents:[]}]},
    {...start,changes:[{key:'task:task1',field:'__proto__',value:{polluted:true},parents:[]}]},
    {...start,changes:[{key:'task:task1',field:'title',value:{polluted:true},parents:[]}]},
    {...start,changes:[{key:'task:task1',field:'id',value:'other',parents:[]}]},
    {...start,changes:[{key:'task:task1',field:'created_at',value:'not-a-date',parents:[]}]},
    {...start,extra:'private'},
  ])assert.throws(()=>mergeJournal([bad]));
  assert.equal({}.polluted,undefined);
});
test('cyclic history and duplicate parents cannot silently erase a field',()=>{
  const a={version:1,id:'operation_0002',actor,when,changes:[{key:'task:task1',field:'title',value:'Bread',parents:['operation_0003']}]};
  const b={version:1,id:'operation_0003',actor,when,changes:[{key:'task:task1',field:'title',value:'Eggs',parents:['operation_0002']}]};
  assert.throws(()=>materialize([start,a,b]),/cycle/);
  assert.throws(()=>mergeJournal([{...a,changes:[{...a.changes[0],parents:[start.id,start.id]}]}]),/history/);
});
const child={id:'entry1',thread_id:'task1',kind:'action',body:'Buy bread',done:0,due_at:null,revisit_at:null,created_at:when};
const note={id:'note1',action_id:'entry1',body:'Wholegrain',created_at:when,updated_at:when};
const family={...initial,'entry:entry1':child,'note:note1':note};
test('child edits conflict with concurrent parent deletion and keep both choices',()=>{
  const root=makeChanges([],{},family,actor,'operation_0100',when),edited=structuredClone(family);edited['note:note1'].body='White bread';
  const del=makeChanges([root],family,{},actor,'operation_0101',when),edit=makeChanges([root],family,edited,'device_99999','operation_0102',when),log=[root,del,edit];
  const out=materialize(log,edited);assert.equal(out.records['note:note1'].body,'White bread');assert.ok(out.conflicts.some(c=>c.key==='task:task1'&&c.field==='$exists'));
  const chooseDelete=resolve(log,'task:task1','$exists',false,actor,'operation_0103');
  assert.deepEqual(materialize([...log,chooseDelete],edited).records,{});
  assert.deepEqual(materialize(mergeJournal([chooseDelete,edit,del],[root,root]),edited).records,{});
});
test('recursive delete removes dependent notes and late replay does not revive them',()=>{
  const root=makeChanges([],{},family,actor,'operation_0200',when),deleted=makeChanges([root],family,{},actor,'operation_0201',when);
  assert.deepEqual(materialize([root,deleted]).records,{});
  assert.deepEqual(materialize(mergeJournal([deleted,root],[root])).records,{});
  assert.throws(()=>materialize([deleted]),/incomplete/);
});
test('resolution needs complete history and converges for reordered delivery',()=>{
  const a=structuredClone(initial),b=structuredClone(initial);a['task:task1'].title='Bread';b['task:task1'].title='Eggs';
  const x=makeChanges([start],initial,a,actor,'operation_0301',when),y=makeChanges([start],initial,b,'device_99999','operation_0302',when),log=[start,x,y];
  const fixed=resolve(log,'task:task1','title','Eggs',actor,'operation_0303');
  assert.throws(()=>materialize([start,x,fixed]),/incomplete/);
  assert.throws(()=>resolve(log,'task:task1','title','Butter',actor,'operation_0304'),/preserved/);
  assert.deepEqual(materialize([fixed,y,start,x]),materialize([start,x,y,fixed]));
});
test('remote reminder dates reset local claims but leave other private state',()=>{
  const state={tasks:[{...task,notified_for:'old',recurring_notified_for:'old',action_prompt:'private'}],entries:[{...child,notified_for:'old'}],notes:[]};
  const records=project(state);records['task:task1'].revisit_at='2027-01-01T00:00:00Z';records['task:task1'].next_occurrence='2027-01-02T00:00:00Z';records['entry:entry1'].revisit_at='2027-01-01T00:00:00Z';
  applyToState(state,records);assert.equal(state.tasks[0].notified_for,null);assert.equal(state.tasks[0].recurring_notified_for,null);assert.equal(state.entries[0].notified_for,null);assert.equal(state.tasks[0].action_prompt,'private');
});
test('derived updated_at compares absolute instants rather than timezone strings',()=>{
  const a=structuredClone(initial);a['task:task1'].title='Bread';const x=makeChanges([start],initial,a,actor,'operation_0401','2026-10-28T01:00:00-04:00');
  assert.equal(materialize([start,x]).records['task:task1'].updated_at,'2026-10-28T01:00:00-04:00');
});

test('plain records from the same-origin parent frame are accepted',async()=>{
 const vm=await import('node:vm');const foreign=vm.runInNewContext('JSON.parse('+JSON.stringify(JSON.stringify(initial))+')');
 const op=makeChanges([],{},foreign,actor,'operation_foreign',when);assert.equal(materialize([op]).records['task:task1'].title,'Milk');
});
