import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { handleRequest } from '../src/routes.ts';

const V6_SAMPLE = `VERSION: 6
SCENARIO: Golden
TEST_STEP:
  NAME 'Pressure'
  VAL 'Ciśnienie' 'bar'
  RANGE 'Ciśnienie' '10 bar' .. '100 bar'
  PASS 'Ciśnienie' 'dobrze'
  FAIL 'Ciśnienie' 'źle'
`;

const V6_TEST_STEP_SAMPLE = `VERSION: 6
TASK:
  NAME 'Przygotowanie'
  SET 'PUMP' 'off'
TEST_STEP:
  NAME 'Szczelność po 60 sekundach'
  MIN 'PI1' '-10.1 mbar'
  VAL 'PI1' 'mbar'
  MAX 'PI1' '-10.1 mbar'
  PASS 'PI1' 'Po 60 sekundach ciśnienie nie przekracza -9.0 mbar'
  FAIL 'PI1' 'Po 60 sekundach ciśnienie przekracza -9.0 mbar'
`;

describe('OQL v6-only runtime boundary via @semcod/oqlts', () => {
  it('parse maps canonical TASK RANGE/PASS/FAIL to the compatibility AST', async () => {
    const res = await handleRequest('POST', '/api/oql/parse', { text: V6_SAMPLE });
    assert.equal(res?.status, 200);
    const body = res?.body as { ok: boolean; ast: { goals: Array<{ steps: unknown[] }> } };
    assert.equal(body.ok, true);
    const steps = body.ast.goals[0].steps;
    assert.deepEqual(steps[0], { type: 'val', parameter: 'Ciśnienie', unit: 'bar' });
    assert.deepEqual(steps[1], { type: 'min', parameter: 'Ciśnienie', value: '10', unit: 'bar' });
    assert.deepEqual(steps[2], { type: 'max', parameter: 'Ciśnienie', value: '100', unit: 'bar' });
    assert.deepEqual(steps[3], { type: 'pass', parameter: 'Ciśnienie', message: 'dobrze' });
    assert.deepEqual(steps[4], { type: 'fail', parameter: 'Ciśnienie', message: 'źle' });
    assert.equal(steps.length, 5);
  });

  it('routes VERSION 6 TASK/TEST_STEP through the canonical parser', async () => {
    const res = await handleRequest('POST', '/api/oql/parse', { text: V6_TEST_STEP_SAMPLE });
    assert.equal(res?.status, 200);
    const body = res?.body as {
      ok: boolean;
      errors: string[];
      ast: { goals: Array<{ name: string; steps: Array<{ type: string }> }> };
    };
    assert.equal(body.ok, true, body.errors.join('\n'));
    assert.deepEqual(body.ast.goals.map((goal) => goal.name), [
      'Przygotowanie',
      'Szczelność po 60 sekundach',
    ]);
    assert.deepEqual(body.ast.goals[1].steps.map((step) => step.type), [
      'min',
      'val',
      'max',
      'pass',
      'fail',
    ]);
  });

  for (const [label, text] of [
    ['VERSION 3', 'VERSION: 3\nSCENARIO: test\nGOAL: test\n  SET "x" "5"'],
    ['VERSION 4', 'VERSION: 4\nSCENARIO: test\nGOAL: test\n  SET "x" "5"'],
    ['VERSION 5', 'VERSION: 5\nSCENARIO: test\nTASK:\n  NAME "test"'],
    ['missing VERSION', 'SCENARIO: test\nGOAL: test\n  SET "x" "5"'],
  ]) {
    it(`rejects ${label} and points to the V6 migrator`, async () => {
      for (const endpoint of ['parse', 'validate', 'exec', 'exec-mapped']) {
        const res = await handleRequest('POST', `/api/oql/${endpoint}`, { text });
        assert.equal(res?.status, 200);
        const body = res?.body as { ok: boolean; errors: string[]; ast: unknown; plan?: unknown[] };
        assert.equal(body.ok, false, endpoint);
        if (endpoint !== 'validate') assert.equal(body.ast, null, endpoint);
        assert.match(body.errors.join('\n'), /wyłącznie VERSION: 6/i, endpoint);
        assert.match(body.errors.join('\n'), /migrateOqlToV6/, endpoint);
        if (endpoint.includes('exec')) assert.deepEqual(body.plan, [], endpoint);
      }
    });
  }

  it('advertises V6 as the only runtime version and V3-V5 as migration inputs', async () => {
    const res = await handleRequest('GET', '/api/oql/capabilities', {});
    const body = res?.body as {
      runtime_oql_version: number;
      accepted_oql_versions: number[];
      migration_input_versions: number[];
    };
    assert.equal(body.runtime_oql_version, 6);
    assert.deepEqual(body.accepted_oql_versions, [6]);
    assert.deepEqual(body.migration_input_versions, [3, 4, 5]);
  });

  it('exec-mapped parses V6 through the same SSOT boundary as exec', async () => {
    const res = await handleRequest('POST', '/api/oql/exec-mapped', {
      text: "VERSION: 6\nTASK:\n  NAME 'Prepare'\n  SET 'pump' 'off'",
      hardware_map: {},
    });
    const body = res?.body as { ok: boolean; errors: string[]; plan: unknown[]; mappedPlan: unknown[] };
    assert.equal(body.ok, true, body.errors.join('\n'));
    assert.deepEqual(body.mappedPlan, body.plan);
  });

  it('rejects a V5 HUI document before compilation', async () => {
    const res = await handleRequest('POST', '/api/oql/compile-hui', {
      text: 'VERSION: 5\nEVENT \'frontend.ready\':\n  LOG \'old\'',
    });
    const body = res?.body as { ok: boolean; program: unknown; errors: string[] };
    assert.equal(body.ok, false);
    assert.equal(body.program, null);
    assert.match(body.errors.join('\n'), /migrateOqlToV6/);
  });
});
