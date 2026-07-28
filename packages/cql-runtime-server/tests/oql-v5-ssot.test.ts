import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { handleRequest } from '../src/routes.ts';

const V5_SAMPLE = `VERSION: 5
SCENARIO: Golden
TASK:
  NAME 'Pressure'
  RANGE 'Ciśnienie' '10 bar' .. '100 bar'
  PASS 'Ciśnienie' 'dobrze'
  FAIL 'Ciśnienie' 'źle'
`;

describe('oql v5 SSOT via @semcod/oqlts', () => {
  it('parse maps canonical TASK RANGE/PASS/FAIL to the compatibility AST', async () => {
    const res = await handleRequest('POST', '/api/oql/parse', { text: V5_SAMPLE });
    assert.equal(res?.status, 200);
    const body = res?.body as { ok: boolean; ast: { goals: Array<{ steps: unknown[] }> } };
    assert.equal(body.ok, true);
    const steps = body.ast.goals[0].steps;
    assert.deepEqual(steps[0], { type: 'min', parameter: 'Ciśnienie', value: '10', unit: 'bar' });
    assert.deepEqual(steps[1], { type: 'max', parameter: 'Ciśnienie', value: '100', unit: 'bar' });
    assert.deepEqual(steps[2], { type: 'pass', parameter: 'Ciśnienie', message: 'dobrze' });
    assert.deepEqual(steps[3], { type: 'fail', parameter: 'Ciśnienie', message: 'źle' });
    assert.equal(steps.length, 4);
  });

  it('legacy v3 still uses block parser', async () => {
    const res = await handleRequest('POST', '/api/oql/parse', {
      text: 'SCENARIO: test\nGOAL: test\n  SET "x" "5"',
    });
    assert.equal(res?.status, 200);
    const body = res?.body as { ok: boolean; ast: { scenario: string } };
    assert.equal(body.ok, true);
    assert.equal(body.ast.scenario, 'test');
  });
});
