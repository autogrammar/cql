import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { handleRequest } from '../src/routes.ts';

type ExtensionCase = {
  id: string;
  endpoint: string;
  body: Record<string, unknown>;
  expectNode: Record<string, unknown>;
};

const here = dirname(fileURLToPath(import.meta.url));
const cases = JSON.parse(
  readFileSync(join(here, 'golden', 'cases-python-extensions.json'), 'utf8'),
) as ExtensionCase[];

function planKinds(body: Record<string, unknown>): string[] {
  const plan = body.plan;
  if (!Array.isArray(plan)) return [];
  return plan.map((step) => String((step as { kind?: string }).kind ?? ''));
}

for (const testCase of cases) {
  describe(`extension:${testCase.id}`, () => {
    it('documents current Node runtime behavior (Python port may differ)', async () => {
      const res = await handleRequest('POST', `/api/oql/${testCase.endpoint}`, testCase.body);
      assert.equal(res?.status, 200);
      const body = res?.body as Record<string, unknown>;
      const expect = testCase.expectNode;
      if (typeof expect.ok === 'boolean') assert.equal(body.ok, expect.ok);
      if (Array.isArray(expect.planKinds)) {
        assert.deepEqual(planKinds(body), expect.planKinds);
      }
    });
  });
}
