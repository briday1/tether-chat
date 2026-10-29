import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.window={};
globalThis.document={createElement:()=>({getContext:()=>({measureText:text=>({width:text.length*7})})})};
const {calendarSVG}=await import('../../web/calendar-export.mjs');
const data=(start,end,week_start)=>{const days=[];for(let d=new Date(start+'T12:00Z');d<=new Date(end+'T12:00Z');d.setUTCDate(d.getUTCDate()+1))days.push({date:d.toISOString().slice(0,10),tasks:[],activity:[]});return {start,end,week_start,days}};
test('exports always show Sunday–Saturday regardless of reminder preference',()=>{
 for(const preference of [0,1,2,3,4,5,6]){
  const {svg}=calendarSVG(data('2026-11-01','2026-11-07',preference));
  assert.deepEqual([...svg.matchAll(/font-size="12">(Sun|Mon|Tue|Wed|Thu|Fri|Sat)<\/text>/g)].map(m=>m[1]),['Sun','Mon','Tue','Wed','Thu','Fri','Sat']);
  assert.equal((svg.match(/<g opacity=/g)||[]).length,7);
 }
});
test('month offsets and empty weekend exports include Sunday boundaries',()=>{
 const month=calendarSVG(data('2026-10-01','2026-10-31',3)).svg;
 assert.equal((month.match(/<g opacity=/g)||[]).length,35);
 assert.match(month,/>27<\/text>/);
 assert.equal((calendarSVG(data('2026-10-31','2026-11-01',1)).svg.match(/<g opacity=/g)||[]).length,14);
 const single=calendarSVG(data('2026-11-01','2026-11-01',3)).svg;
 assert.equal((single.match(/<g opacity=/g)||[]).length,1);
 assert.doesNotMatch(single,/>Sun<\/text>/);
});
