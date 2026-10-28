import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {sealHouseholdBundle,openHouseholdBundle,inspectHouseholdBundle,validateHouseholdAIConfig,normalizeHouseholdProvider,HOUSEHOLD_AI_ITERATIONS} from '../../web/household-ai-crypto.mjs';
import {CompactEncrypt,decodeProtectedHeader} from '../../web/vendor-jose.mjs';
const binding={householdId:'household_synthetic01',revisionId:'revision_synthetic01'};
const passphrase='synthetic calm amber winter words';
const config={base_url:'https://api.example.com/v1',model:'synthetic-tool-model',api_key:'synthetic-never-real-key'};
const jwe=await sealHouseholdBundle(config,passphrase,binding);
const b64=value=>Buffer.from(JSON.stringify(value)).toString('base64url');
function headerChange(changes){const parts=jwe.split('.');parts[0]=b64({...decodeProtectedHeader(jwe),...changes});return parts.join('.')}

test('standard compact JWE round trip authenticates household/revision and normalizes URL',async()=>{
  assert.equal(jwe.split('.').length,5);
  assert.deepEqual(inspectHouseholdBundle(jwe,binding),{version:1,...binding});
  assert.deepEqual(await openHouseholdBundle(jwe,passphrase,binding),config);
  assert.equal(decodeProtectedHeader(jwe).p2c,HOUSEHOLD_AI_ITERATIONS);
  assert.ok(!jwe.includes(config.api_key));assert.ok(!jwe.includes(passphrase));
  assert.equal(normalizeHouseholdProvider('https://API.EXAMPLE.COM:443/v1/'),'https://api.example.com/v1');
});
test('fresh encryption uses independent salts and IVs even for identical inputs',async()=>{
  const other=await sealHouseholdBundle(config,passphrase,binding);
  assert.notEqual(other,jwe);assert.notEqual(decodeProtectedHeader(other).p2s,decodeProtectedHeader(jwe).p2s);
  assert.notEqual(other.split('.')[2],jwe.split('.')[2]);
});
test('wrong passphrase and ciphertext corruption fail without echoing secrets',async()=>{
  for(const [candidate,password] of [[jwe,'other synthetic passphrase words'],[(()=>{const p=jwe.split('.');p[3]=(p[3][0]==='A'?'B':'A')+p[3].slice(1);return p.join('.')})(),passphrase]]){
    await assert.rejects(openHouseholdBundle(candidate,password,binding),error=>{
      assert.ok(!error.message.includes(config.api_key));assert.ok(!error.message.includes(passphrase));return /Could not unlock/.test(error.message);
    });
  }
});
test('copied bundle cannot be opened for another household or revision',async()=>{
  for(const other of [{...binding,householdId:'another_household01'},{...binding,revisionId:'another_revision01'}])
    await assert.rejects(openHouseholdBundle(jwe,passphrase,other),/Unsupported/);
});
test('reject algorithm, header extensions and adversarial KDF parameters before decrypt',()=>{
  for(const change of [{alg:'dir'},{enc:'A128GCM'},{v:2},{p2c:1},{p2c:1e12},{p2c:'220000'},{jku:'https://evil.example/key'},{jwk:{}},{x5u:'https://evil.example/cert'},{crit:['v']},{zip:'DEF'},{p2s:'AA'}])
    assert.throws(()=>inspectHouseholdBundle(headerChange(change),binding),/Unsupported/);
});
test('reject malformed and oversized compact structures before crypto',()=>{
  for(const bad of ['',null,{},'a.b.c','.'.repeat(25000),jwe+'=',jwe.replaceAll('.','..')])assert.throws(()=>inspectHouseholdBundle(bad,binding),/Unsupported/);
  for(const i of [1,2,4]){const parts=jwe.split('.');parts[i]='AA';assert.throws(()=>inspectHouseholdBundle(parts.join('.'),binding),/Unsupported/)}
});
test('provider guard rejects credentials, query, fragments, local/IP targets and URL parser tricks',()=>{
  for(const url of ['http://api.example.com/v1','https://me:pass@api.example.com/v1','https://api.example.com/v1?key=x','https://api.example.com/#key','https://localhost/v1','https://x.local/v1','https://server.internal/v1','https://127.0.0.1/v1','https://0x7f000001/v1','https://[::1]/v1','https://192.168.0.1/v1','https://api.example.com./v1','https://api.example.com\\evil','https://api.\nexample.com/v1','https://intranet/v1'])assert.throws(()=>normalizeHouseholdProvider(url),/HTTPS/);
  assert.equal(normalizeHouseholdProvider('https://api.example.com:8443/openai/v1'),'https://api.example.com:8443/openai/v1');
});
test('config is bounded, field-whitelisted and accepts ordinary cross-realm records',()=>{
  for(const bad of [{...config,extra:'hidden'},{...config,api_key:''},{...config,api_key:'x'.repeat(10001)},{...config,api_key:'contains space'},{...config,model:'\nmodel'},{...config,model:'x'.repeat(201)},{...config,base_url:'https://api.example.com/'+'x'.repeat(2048)}])assert.throws(()=>validateHouseholdAIConfig(bad));
  assert.deepEqual(validateHouseholdAIConfig(vm.runInNewContext('('+JSON.stringify(config)+')')),config);
});
test('passphrase minimum and maximum enforced on creation and unlock',async()=>{
  for(const password of ['short','x'.repeat(1025)]){
    await assert.rejects(sealHouseholdBundle(config,password,binding),/passphrase/);
    await assert.rejects(openHouseholdBundle(jwe,password,binding),/passphrase/);
  }
});
test('authenticated but wrong inner schema/binding is rejected',async()=>{
  for(const data of [{...config,v:1,...binding,householdId:'another_household01'},{...config,v:1,...binding,extra:'hidden'}]){
    const encrypted=await new CompactEncrypt(new TextEncoder().encode(JSON.stringify(data)))
      .setProtectedHeader({alg:'PBES2-HS512+A256KW',enc:'A256GCM',typ:'tether-household-ai+jwe',v:1,household:binding.householdId,revision:binding.revisionId})
      .setKeyManagementParameters({p2c:HOUSEHOLD_AI_ITERATIONS,p2s:crypto.getRandomValues(new Uint8Array(16))})
      .encrypt(new TextEncoder().encode(passphrase));
    await assert.rejects(openHouseholdBundle(encrypted,passphrase,binding),/Could not unlock/);
  }
});
