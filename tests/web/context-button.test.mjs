import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('chat context uses the same compact task utility styling as Edit task',()=>{
  const board=readFileSync(new URL('../../tether/board.html',import.meta.url),'utf8');
  const css=readFileSync(new URL('../../tether/theme.css',import.meta.url),'utf8');
  assert.match(board,/el\('button','secondary task-context-button','Use as chat context'\)/);
  const rule=css.match(/\.actions-section \.edit-task-button,\.actions-section \.task-context-button\{([^}]+)\}/)?.[1];
  assert.ok(rule,'Both controls must share one compact sizing rule');
  for(const property of ['width:auto!important','min-height:28px','padding:4px 9px!important','font-size:12px!important','line-height:18px'])assert.ok(rule.includes(property),property);
});
