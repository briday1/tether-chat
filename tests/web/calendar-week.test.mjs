import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {Model,emptyState,snapshotRange} from '../../web/store.mjs';
test('calendar weeks are Sunday through Saturday regardless of reminder preference',()=>{
 for(let preference=0;preference<7;preference++){
  assert.deepEqual(snapshotRange('/snapshot next week',new Date(2026,9,28,12),preference),['2026-11-01','2026-11-07']);
  assert.deepEqual(snapshotRange('/snapshot week',new Date(2026,10,1,12),preference),['2026-11-01','2026-11-07']);
  const m=new Model(emptyState());m.setPreferences({week_start:preference});assert.equal(m.snapshot('2026-11-01','2026-11-07').week_start,0);assert.equal(m.preferences().week_start,preference);
 }
});
test('calendar week follows local Sunday at timezone and DST boundary',()=>{
 const code=`import {snapshotRange} from './web/store.mjs';console.log(JSON.stringify(snapshotRange('/snapshot week',new Date('2026-11-01T03:30:00Z'),3)))`;
 const result=execFileSync(process.execPath,['--input-type=module','-e',code],{env:{...process.env,TZ:'America/New_York'}}).toString().trim();
 assert.equal(result,'["2026-10-25","2026-10-31"]');
});
