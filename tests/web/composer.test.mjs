import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../tether/chat.js',import.meta.url),'utf8');
const helper=source.slice(source.indexOf(' function resizeInput(){'),source.indexOf(" window.addEventListener('resize',resizeInput)"));
function setup({height=900,content=44,bottom=true,visible=true}={}){
 const input={style:{},scrollTop:20,scrollHeight:content,getClientRects:()=>visible?[{}]:[]};
 const chat={scrollHeight:2000,scrollTop:bottom?1700:300,clientHeight:300};
 const context={document:{querySelector:()=>input},chat,window:{innerHeight:height}};
 vm.createContext(context);vm.runInContext(helper,context);
 return {input,chat,context,resize:()=>vm.runInContext('resizeInput()',context)};
}
test('composer grows, caps, scrolls, then shrinks without changing draft or focus',()=>{
 const {input,resize}=setup({content:120});resize();assert.equal(input.style.height,'120px');assert.equal(input.style.overflowY,'hidden');
 input.scrollHeight=800;resize();assert.equal(input.style.height,'200px');assert.equal(input.style.overflowY,'auto');assert.equal(input.scrollTop,20);
 input.scrollHeight=24;resize();assert.equal(input.style.height,'44px');assert.equal(input.style.overflowY,'hidden');
});
test('composer cap follows mobile visual viewport; scrollback is not jumped',()=>{
 const {input,chat,context,resize}=setup({content:800,bottom:false});context.window.visualViewport={height:300};resize();assert.equal(input.style.height,'90px');assert.equal(chat.scrollTop,300);
 context.window.visualViewport.height=100;resize();assert.equal(input.style.height,'44px');
});
test('hidden retained composer defers measurement until reopened',()=>{
 const {input,resize}=setup({visible:false});resize();assert.deepEqual(input.style,{});
});
test('all programmatic draft paths and input use shared resizing',()=>{
 assert.match(source,/input\.value=payload\.text;resizeInput\(\)/);
 assert.match(source,/input\.value='';resizeInput\(\)/);
 assert.match(source,/input\.addEventListener\('input',\(\)=>\{resizeInput\(\)/);
 assert.match(source,/resizeInput\(\);\s*refreshReferences\(\);sync\(\);reminders\(\)/);
 const html=readFileSync(new URL('../../tether/index.html',import.meta.url),'utf8');
 assert.ok(!html.includes('Enter to send · Shift+Enter for new line'));
 assert.ok(html.includes("e.key==='Enter'&&!e.shiftKey"));
});
