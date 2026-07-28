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
const cases = JSON.parse(readFileSync(join(here, 'golden', 'cases-mapping.json'), 'utf8')) as GoldenCase[];

for (const testCase of cases) {
  describe(`golden-mapping:${testCase.id}`, () => {
    it('resolves hardware MAP bindings', async () => {
      const res = await handleRequest('POST', `/api/oql/${testCase.endpoint}`, testCase.body);
      const body = res?.body as Record<string, unknown>;
      const expect = testCase.expect;
      assert.equal(res?.status, expect.ok === false ? 400 : 200, `${testCase.id} status`);
      if (typeof expect.ok === 'boolean') assert.equal(body.ok, expect.ok);
      if (expect.mappingCommand) {
        const mapping = body.mapping as { body?: { command?: string } };
        assert.equal(mapping?.body?.command, expect.mappingCommand);
      }
      if (expect.stepsResolved !== undefined) {
        const steps = body.steps as unknown[];
        assert.equal(steps?.length, expect.stepsResolved);
        assert.equal((steps?.[0] as { resolved?: boolean })?.resolved, true);
      }
    });
  });
}
