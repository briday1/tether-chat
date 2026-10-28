import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import fs from 'node:fs';

test('workspace routes never corrupt blob downloads or external links',()=>{
 const handlers={},window={fetch:()=>{}},location={href:'https://tether.test/?workspace=home',search:'?workspace=home',origin:'https://tether.test'};
 const document={addEventListener:(name,fn)=>handlers[name]=fn};
 vm.runInNewContext(fs.readFileSync(new URL('../../tether/workspace.js',import.meta.url),'utf8'),{window,document,location,URL,URLSearchParams,Headers,Request});
 for(const href of ['blob:https://tether.test/1234','https://other.test/board']){
   const link={href};handlers.click({target:{closest:()=>link}});assert.equal(link.href,href);
 }
 const link={href:'https://tether.test/api/backup'};handlers.click({target:{closest:()=>link}});
 assert.equal(link.href,'https://tether.test/api/backup?workspace=work');
 assert.equal(window.tetherWorkspace,'work');
});
