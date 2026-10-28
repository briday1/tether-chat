import test from 'node:test';
import assert from 'node:assert/strict';
import {configVersion} from '../../web/launch.mjs';

test('launch checks read both legacy and current configuration assignments',()=>{
  assert.equal(configVersion('window.TETHER_CONFIG={"version":"2026.23"};'),'2026.23');
  assert.equal(configVersion('window.TETHER_CONFIG = {"version":"2026.24","system":"a = b"};\n'),'2026.24');
});
test('launch configuration parsing never evaluates script content',()=>{
  assert.throws(()=>configVersion('window.TETHER_CONFIG = {}; globalThis.injected=true;'));
  assert.throws(()=>configVersion('<html>Unavailable</html>'));
  assert.equal(globalThis.injected,undefined);
});
