import test from 'node:test';
import assert from 'node:assert/strict';
import {providerFailure,retryDelay} from '../../web/provider.mjs';

test('retry delays support seconds and HTTP dates without shortening the server delay',()=>{
  assert.equal(retryDelay('120'),120);
  assert.equal(retryDelay('Tue, 27 Oct 2026 12:02:00 GMT',0,Date.parse('2026-10-27T12:00:00Z')),120);
  assert.equal(retryDelay('0'),0);assert.ok(retryDelay(null,1)>=2);
});
test('provider error details never expose keys and malformed responses remain actionable',async()=>{
  const failure=await providerFailure(Response.json({error:{message:'Unsupported model; key synthetic-secret sk-another-secret'}},{status:400}),
    'synthetic-secret','https://provider.test/v1');
  assert.ok(!failure.message.includes('synthetic-secret'));assert.ok(!failure.message.includes('sk-another-secret'));
  assert.match(failure.message,/Unsupported model/);assert.equal(failure.retryable,false);
  const html=await providerFailure(new Response('<html>Bad gateway</html>',{status:502}),'key','https://provider.test/v1');
  assert.equal(html.retryable,true);assert.match(html.message,/HTTP 502/);
});
