import test from 'node:test';
import assert from 'node:assert/strict';
import {buildHouseholdInvite,parseHouseholdInvite} from '../../web/household-invite.mjs';
const base='https://briday1.github.io/tether-chat/';
const home={id:'abc_123-456',name:'Tether · Brian & Jane’s Home'};
const link=payload=>base+'#'+new URLSearchParams({tetherInvite:typeof payload==='string'?payload:JSON.stringify(payload)});
const invalid=fn=>assert.throws(fn,/invalid.*new invitation/);
test('invitation round trips a versioned file identifier and display name in the fragment',()=>{
  const result=buildHouseholdInvite(base+'?view=sharing&keep=1#old',home),url=new URL(result);
  assert.equal(url.origin,'https://briday1.github.io');assert.equal(url.pathname,'/tether-chat/');
  assert.equal(url.searchParams.get('settings'),'sharing');assert.equal(url.searchParams.get('keep'),'1');assert.equal(url.searchParams.has('view'),false);
  assert.equal(url.search.includes(home.id),false);assert.deepEqual(parseHouseholdInvite(result),home);
  assert.deepEqual(JSON.parse(new URLSearchParams(url.hash.slice(1)).get('tetherInvite')),{v:1,...home});
});
test('normal links without an invitation remain ordinary app links',()=>{
  for(const suffix of ['', '?settings=sharing','#other=section','?tetherInvite=not-an-invite'])assert.equal(parseHouseholdInvite(base+suffix),null);
});
test('malformed, ambiguous, oversized and unsupported invitation payloads fail closed',()=>{
  for(const value of ['', '{',null,[],1,{v:2,...home},{...home},{v:1,...home,token:'secret'},JSON.parse('{"v":1,"id":"abc","name":"Home","__proto__":{}}')])invalid(()=>parseHouseholdInvite(link(value)));
  invalid(()=>parseHouseholdInvite(link({v:1,...home})+'&tetherInvite=second'));
  invalid(()=>parseHouseholdInvite(base+'#tetherInvite=%ZZ'));
  invalid(()=>parseHouseholdInvite(base+'#tetherInvite='+ 'a'.repeat(4097)));
});
test('file IDs cannot become paths, URLs or executable content',()=>{
  for(const id of ['', 'short', '../abc','https://evil.example/a','abc/def','abc?x=1','abc#x','abc%2fdef','<script>', 'a'.repeat(201),null,123]){
    invalid(()=>buildHouseholdInvite(base,{...home,id}));invalid(()=>parseHouseholdInvite(link({v:1,...home,id})));
  }
});
test('display names are bounded plain data, not executable markup',()=>{
  for(const name of ['', '  ', 'x'.repeat(201),'home\nother','home\u0000other','home\u202eevil',null,123]){
    invalid(()=>buildHouseholdInvite(base,{...home,name}));invalid(()=>parseHouseholdInvite(link({v:1,...home,name})));
  }
  const name='<img src=x onerror=alert(1)> & #?';
  assert.deepEqual(parseHouseholdInvite(buildHouseholdInvite(base,{...home,name})),{...home,name});
  assert.equal(parseHouseholdInvite(buildHouseholdInvite(base,{...home,name:' Home '})).name,'Home');
});
test('unsafe URL schemes and embedded credentials are rejected',()=>{
  for(const url of ['javascript:alert(1)','data:text/html,hello','file:///tmp/home','https://user:password@example.org/','/relative']){
    invalid(()=>buildHouseholdInvite(url,home));invalid(()=>parseHouseholdInvite(url));
  }
});
