import test from 'node:test';
import assert from 'node:assert/strict';
import {recoveryFiles,readLegacy} from '../../web/legacy-recovery.mjs';
import {emptyState,Model} from '../../web/store.mjs';
test('legacy recovery preserves Work and drafts without copying plaintext keys or resuming jobs',()=>{
 const state=emptyState();new Model(state).create('Private work');state.settings={base_url:'https://example.test',model:'x',encrypted_key:{ciphertext:'encrypted'},api_key:'never-export'};
 state.jobs=[{status:'queued'}];const before=structuredClone(state);
 const storage={getItem:key=>({'tether-web-draft:/app/':'draft','tether-web-outbox:/app/':'pending'}[key]||null)};
 const files=recoveryFiles(state,storage,'/app/');assert.equal(files.portable.workspace,'work');assert.equal(files.privateRecovery.draft,'draft');assert.equal(files.privateRecovery.outbox,'pending');assert.equal(files.privateRecovery.connection.encrypted_key.ciphertext,'encrypted');assert.ok(!JSON.stringify(files).includes('never-export'));assert.deepEqual(state,before);assert.ok(!files.portable.data.jobs);
});
test('absent legacy database creation is aborted',async()=>{
 let aborted=false;const indexedDB={open(){const r={transaction:{abort(){aborted=true;queueMicrotask(()=>r.onerror())}}};queueMicrotask(()=>r.onupgradeneeded());return r}};
 assert.equal(await readLegacy('/app/',{indexedDB}),null);assert.equal(aborted,true);
});
