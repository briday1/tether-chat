import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {resolveReminder,reminderIntent,preferences} from '../../web/decisions.mjs';
test('beginning-of-week reminder preference preserves every day and explicit scheduling',()=>{
 const now=new Date(2026,9,28,15);
 for(let day=0;day<7;day++){
  const saved={week_start:day};assert.equal(preferences(saved).week_start,day);
  assert.equal(new Date(resolveReminder('beginning of next week',saved,now)).getDay(),day);
  assert.equal(resolveReminder('next week on Tuesday',saved,now),new Date(2026,10,3,9).toISOString());
  assert.equal(resolveReminder('2026-11-05',saved,now),new Date(2026,10,5,9).toISOString());
  assert.equal(resolveReminder(reminderIntent('Remind me next week on 2026-11-05 at 3pm'),saved,now),new Date(2026,10,5,15).toISOString());
  assert.equal(resolveReminder(reminderIntent('Remind me next week on Tuesday at 3pm'),saved,now),new Date(2026,10,3,15).toISOString());
 }
});
test('beginning-of-week reminder uses local date across DST',()=>{
 const actual=execFileSync(process.execPath,['--input-type=module','-e',`import {resolveReminder} from './web/decisions.mjs';console.log(resolveReminder('beginning of next week',{week_start:0},new Date('2026-11-01T03:30:00Z')));`],{cwd:new URL('../../',import.meta.url),env:{...process.env,TZ:'America/New_York'}}).toString().trim();
 assert.equal(actual,'2026-11-01T14:00:00.000Z');
});
