import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderMarkdown} from '../../web/render.mjs';
import {briefNote,taskNote,checkInNote} from '../../web/notes.mjs';

const config={base:'/tether-chat/'};
const examples=JSON.parse(readFileSync(new URL('../fixtures/note-replies.json',import.meta.url),'utf8'));
for(const example of examples)test('Note example: '+example.name,()=>{
  const html=renderMarkdown(example.markdown,config);
  assert.equal((html.match(/<table>/g)||[]).length,example.tables);
  assert.equal((html.match(/<tr>/g)||[]).length,example.rows+example.tables);
  assert.equal((html.match(/<a /g)||[]).length,example.links);
  assert.ok(!html.includes('<script>'));
  for(const match of html.matchAll(/href="([^"]+)"/g))assert.ok(match[1].startsWith('/tether-chat/board.html#'));
});

test('table cells escape stored Markdown and retain task, action and category references',()=>{
  const task={id:'literal',title:'Review [A] | *draft*',summary:'Keep [this](https://example.invalid) | literal.',
    due_at:'2030-05-01',revisit_at:'2030-05-02T12:00:00Z',state:'waiting',
    entries:[{kind:'action',body:'Check | attachment',done:false,due_at:'2030-05-03',revisit_at:'2030-05-04T12:00:00Z'},{kind:'action',body:'Already done',done:true}]};
  const markdown=briefNote({deadlines:[task],due:[task],active:[],waiting:[task]}),html=renderMarkdown(markdown,config);
  assert.equal((html.match(/<a /g)||[]).length,1);
  assert.equal((html.match(/<td>/g)||[]).length,3);
  assert.ok(html.includes('Review [A] | *draft*'));
  assert.ok(html.includes('Keep [this](https://example.invalid) | literal.'));
  assert.ok(html.includes('Check | attachment (due 2030-05-03; Bring to attention 2030-05-04)'));
  assert.ok(!html.includes('Already done'));
  assert.ok(html.includes('Due 2030-05-01; Bring to attention 2030-05-02; Waiting'));
});

test('unsafe links and formatting cannot escape a text or href boundary',()=>{
  const html=renderMarkdown('[bad](javascript:alert) [ok](https://example.test/**bold**) <img src=x onerror=alert(1)> `**literal**`',config);
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('href="https://example.test/**bold**"'));
  assert.ok(html.includes('<code>**literal**</code>'));
  assert.ok(!html.includes('<strong>bold</strong>'));
});

test('tables inside code are literal, and a malformed row is not silently dropped',()=>{
  const code='```\n| Task | When |\n| --- | --- |\n| A | B |\n```';
  assert.ok(!renderMarkdown(code,config).includes('<table>'));
  const html=renderMarkdown('| Task | When |\n| --- | --- |\n| A | B |\n| extra | cells | retained |',config);
  assert.ok(html.includes('extra | cells | retained'));
});

test('older task lists retain their nested notes and ordered steps',()=>{
  const html=renderMarkdown('- [Task](/board#task/one) — Context\n  - Keep this note under the task.\n- [Other](/board#task/two)\n\n1. First step\n2. Second step',config);
  assert.ok(html.includes('Context<ul><li>Keep this note under the task.</li></ul></li>'));
  assert.ok(html.includes('<ol><li>First step</li><li>Second step</li></ol>'));
});

test('short and empty notes do not acquire unnecessary structure',()=>{
  assert.equal(renderMarkdown('Saved the note.',config),'<p>Saved the note.</p>');
  assert.ok(!taskNote('Matches',[]).includes('| Task'));
  const rows=[{id:'1',title:'First'},{id:'2',title:'Second'}];
  assert.ok(taskNote('Matches',rows,undefined,1).includes('Showing 1 of 2 tasks'));
  const task={id:'task',title:'Parent',summary:'Shared context',revisit_at:'2030-05-06T12:00:00Z'};
  const action={body:'Selected action',due_at:'2030-05-01',notes:[{body:'Only this action.'}]};
  const note=checkInNote(task,action,'/board#action/task/action');
  assert.ok(note.includes('2030-05-01')&&!note.includes('2030-05-06'));
});

test('date-only next occurrence remains the same calendar date west of UTC',()=>{
  const previous=process.env.TZ;process.env.TZ='America/Los_Angeles';
  try {
    const note=checkInNote({id:'repeat',title:'Tomorrow',recurrence:'daily',next_occurrence:'2026-10-30'},null,'/board#task/repeat');
    assert.ok(note.includes('2026-10-30'));assert.ok(!note.includes('Oct 29'));
  } finally {if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous}
});
test('deadline and schedule labels use viewer-local day without shifting date-only values',()=>{
 const previous=process.env.TZ;
 try{process.env.TZ='America/Los_Angeles';
 const task={id:'dates',title:'Dates',due_at:'2026-10-30T00:30:00Z',revisit_at:'2026-10-30T00:30:00Z',recurrence:'daily',next_occurrence:'2026-10-30T00:30:00Z',entries:[{kind:'action',body:'Calendar deadline',due_at:'2026-10-30'}]};
 const table=taskNote('Dates',[task]),check=checkInNote(task,null,'/board#task/dates');
 assert.ok(table.includes('Due 2026-10-29')&&table.includes('Bring to attention 2026-10-29')&&table.includes('Next occurrence 2026-10-29'));
 assert.ok(table.includes('due 2026-10-30'));assert.ok(check.includes('| Due date | 2026-10-29 |'));
 }finally{if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous}
});
