import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../../tether/snapshot.html',import.meta.url),'utf8');
const ctx=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function displayPacking('),source.indexOf('function displayContext(')),ctx);
const pack=(h,w,n,contexts=[])=>JSON.parse(JSON.stringify(ctx.displayPacking(h,w,n,contexts)));
function used(p){if(p.headerOverflow)return p.visible*p.rowHeight+Math.max(0,p.visible-1)*p.gap;return p.visible*p.rowHeight+Math.max(0,p.visible-1)*p.gap+p.contexts.filter(Boolean).length*14+(p.more?p.moreHeight+(p.visible?p.gap:0):0)}
test('large dashboard cells fit more than three titles and reserve overflow',()=>{
 const p=pack(150,180,18,Array(18).fill(true));assert.equal(p.visible,6);assert.equal(p.more,12);assert.ok(used(p)<=150);assert.ok(p.contexts.every(c=>!c));
});
test('additional context uses only space left after fitting titles',()=>{
 const p=pack(110,180,3,[true,true,true]);assert.equal(p.visible,3);assert.equal(p.more,0);assert.deepEqual(p.contexts,[true,true,true]);assert.ok(used(p)<=110);
 const narrow=pack(110,70,3,[true,true,true]);assert.ok(narrow.text);assert.ok(narrow.contexts.every(c=>!c));
});
test('phone cells use accessible markers and count every hidden item',()=>{
 const p=pack(60,34,18);assert.equal(p.text,false);assert.equal(p.visible,4);assert.equal(p.more,14);assert.ok(used(p)<=60);
 assert.equal(pack(16,34,18).visible,0);assert.equal(pack(16,34,18).more,18);
});
test('packing accounts for every item and never exceeds available practical height',()=>{
 for(const height of [0,1,5,10,15,16,17,18,19,35,50,79,100,155,240])for(const width of [28,61,62,89,90,180])for(const count of [0,1,2,3,9,18,80]){
  const p=pack(height,width,count,Array(count).fill(true));assert.equal(p.visible+p.more,count);assert.ok(used(p)<=height,JSON.stringify({height,width,count,p}));
 }
});
test('dashboard-only packing retains fixed chat markers and stable resize observation',()=>{
 assert.ok(source.includes('if(dashboard&&month){cell.displayRecords=records;'));
 assert.ok(source.includes('records.slice(0,3)'));
 assert.ok(source.includes('new ResizeObserver(queueDisplayPacking)'));
 assert.ok(source.includes('if(cell.packingKey===key)continue'));
 assert.ok(source.includes("item.onclick=()=>selectDate(cell.dataset.date)"));
 assert.ok(source.includes("plan.headerOverflow?cell.querySelector('.day-number'):items"));
});

test('short landscape moves the full overflow count to the date header',()=>{
 for(let h=0;h<16;h++){const p=pack(h,80,18);assert.equal(p.visible,0);assert.equal(p.more,18);assert.equal(p.headerOverflow,true);assert.equal(used(p),0)}
 assert.equal(pack(16,80,18).headerOverflow,false);
});
test('very large overflow labels compact without losing the exact accessible count',()=>{
 assert.equal(ctx.displayOverflowText(18000,30),'+18k');
 assert.equal(ctx.displayOverflowText(18000,20),'+…');
 assert.equal(ctx.displayOverflowText(18,60),'+18 more');
 assert.ok(source.includes("'Show all '+records.length+' items on '"));
});

test('short narrow cells retain any markers that fit beside header overflow',()=>{
 const single=pack(10,34,1);assert.equal(single.visible,1);assert.equal(single.more,0);assert.equal(single.headerOverflow,false);assert.equal(used(single),8);
 const busy=pack(15,34,3);assert.equal(busy.visible,1);assert.equal(busy.more,2);assert.equal(busy.headerOverflow,true);assert.equal(used(busy),8);
});

test('date header geometry is stable when overflow moves in or out',()=>{
 assert.ok(source.includes('.grid.month .day .day-number{display:flex;align-items:center;gap:2px}'));
 assert.ok(source.includes('.grid.month .day .day-date{min-width:0;padding-left:0;padding-right:0;flex:none}'));
 assert.ok(!source.includes('.day.packing-header-overflow .day-number{display:flex'));
});

test('compact context distinguishes deadlines and attention from occurrence times',()=>{
 const context=vm.createContext({Date,scheduleDay:value=>value.slice(0,10)});
 vm.runInContext(source.slice(source.indexOf('function displayContext('),source.indexOf('let packingFrame=')),context);
 assert.match(context.displayContext({date:'2026-11-11',due_at:'2026-11-11T14:30:00Z'},false),/^Due /);
 assert.match(context.displayContext({date:'2026-11-11',revisit_at:'2026-11-11T14:30:00Z'},false),/^Attention /);
 assert.doesNotMatch(context.displayContext({date:'2026-11-11',occurrence_at:'2026-11-11T14:30:00Z'},false),/^(Due|Attention|Logged) /);
 assert.equal(context.displayContext({date:'2026-11-11',due_at:'2026-11-12T14:30:00Z',summary:'Bring the folder'},false),'Bring the folder');
});
