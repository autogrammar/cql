import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { handleRequest } from '../src/routes.ts';

type GoldenCase = {
  id: string;
  endpoint: string;
  body: Record<string, unknown>;
  expect: Record<string, unknown>;
};

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(readFileSync(join(here, 'golden', 'cases.json'), 'utf8')) as GoldenCase[];

function planKinds(body: Record<string, unknown>): string[] {
  const plan = body.plan;
  if (!Array.isArray(plan)) return [];
  return plan.map((step) => String((step as { kind?: string }).kind ?? ''));
}

function lastTask(body: Record<string, unknown>): Record<string, unknown> | null {
  const plan = body.plan;
  if (!Array.isArray(plan)) return null;
  for (let i = plan.length - 1; i >= 0; i -= 1) {
    const row = plan[i] as { kind?: string; task?: Record<string, unknown> };
    if (row.kind === 'task' && row.task) return row.task;
  }
  return null;
}

for (const testCase of cases) {
  describe(`golden:${testCase.id}`, () => {
    it(`matches Node runtime expectations`, async () => {
      const path = `/api/oql/${testCase.endpoint}`;
      const res = await handleRequest('POST', path, testCase.body);
      assert.equal(res?.status, 200, `${testCase.id} HTTP status`);
      const body = res?.body as Record<string, unknown>;
      const expect = testCase.expect;

      if (typeof expect.ok === 'boolean') {
        assert.equal(body.ok, expect.ok, `${testCase.id} ok`);
      }
      if (typeof expect.quoted === 'string') {
        assert.equal(body.quoted, expect.quoted, `${testCase.id} quoted`);
      }
      if (typeof expect.text === 'string') {
        assert.equal(body.text, expect.text, `${testCase.id} text`);
      }
      if (Array.isArray(expect.planKinds)) {
        assert.deepEqual(planKinds(body), expect.planKinds, `${testCase.id} planKinds`);
      }
      if (Array.isArray(expect.planKindsIncludes)) {
        const kinds = planKinds(body);
        for (const kind of expect.planKindsIncludes) {
          assert.ok(kinds.includes(String(kind)), `${testCase.id} missing kind ${kind}`);
        }
      }
      if (expect.scenario) {
        const ast = body.ast as { scenario?: string } | null;
        assert.equal(ast?.scenario, expect.scenario, `${testCase.id} scenario`);
      }
      if (expect.lastTask) {
        const task = lastTask(body);
        assert.ok(task, `${testCase.id} lastTask missing`);
        const wanted = expect.lastTask as Record<string, unknown>;
        for (const [key, value] of Object.entries(wanted)) {
          assert.deepEqual(task[key], value, `${testCase.id} lastTask.${key}`);
        }
      }
    });
  });
}
