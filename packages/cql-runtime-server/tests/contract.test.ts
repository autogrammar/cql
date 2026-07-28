import assert from 'node:assert/strict';
import { once } from 'node:events';
import http from 'node:http';
import { after, before, describe, it } from 'node:test';

import { handleRequest } from '../src/routes.ts';

function request(
  baseUrl: string,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; json: Record<string, unknown> }> {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? undefined : JSON.stringify(body);
    const url = new URL(path, baseUrl);
    const req = http.request(
      url,
      {
        method,
        headers: payload ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) } : {},
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
        res.on('end', () => {
          const raw = Buffer.concat(chunks).toString('utf8');
          resolve({ status: res.statusCode ?? 0, json: raw ? JSON.parse(raw) : {} });
        });
      },
    );
    req.on('error', reject);
    if (payload) req.write(payload);
    req.end();
  });
}

describe('oql-runtime-server routes (in-process)', () => {
  it('health reports node runtime', async () => {
    const res = await handleRequest('GET', '/health', {});
    assert.equal(res?.status, 200);
    assert.equal(res?.body.service, 'oql-runtime-server');
  });

  it('parse + exec minimal DSL', async () => {
    const dsl = [
      'VERSION: 6',
      'SCENARIO: smoke',
      '',
      'TASK:',
      "  NAME 'G1'",
      "  SET 'x' '1'",
    ].join('\n');

    const parsed = await handleRequest('POST', '/api/oql/parse', { text: dsl });
    assert.equal(parsed?.status, 200);
    assert.equal((parsed?.body as { ok: boolean }).ok, true);

    const executed = await handleRequest('POST', '/api/oql/exec', { text: dsl });
    assert.equal(executed?.status, 200);
    assert.equal((executed?.body as { ok: boolean }).ok, true);
    const plan = (executed?.body as { plan: unknown[] }).plan;
    assert.ok(Array.isArray(plan) && plan.length > 0);
  });

  it('projects OQL source according to READ grants without exposing policy declarations', async () => {
    const policy = [
      "ALLOW role:administrator UPDATE *",
      "DENY role:operator READ VAL 'secret'",
      "VAL 'secret'",
      "VAL 'pressure'",
    ].join('\n');

    const operator = await handleRequest('POST', '/api/oql/read-projection', {
      role: 'operator',
      policy_text: policy,
      documents: [{ id: 'scenario', text: policy }],
    });
    assert.equal(operator?.status, 200);
    const operatorDocument = (operator?.body as { documents: Array<{ text: string; hidden_lines: number }> }).documents[0];
    assert.equal(operatorDocument.text, "VAL 'pressure'");
    assert.equal(operatorDocument.hidden_lines, 3);

    const system = await handleRequest('POST', '/api/oql/read-projection', {
      role: 'system',
      policy_text: policy,
      documents: [{ id: 'scenario', text: policy }],
    });
    assert.equal(
      (system?.body as { documents: Array<{ text: string }> }).documents[0].text,
      policy,
    );
  });

  it('compiles the event-driven HUI dialect through the shared OQL runtime', async () => {
    const response = await handleRequest('POST', '/api/oql/compile-hui', {
      system_text: [
        'VERSION: 6',
        'CONFIG:',
        "  PROCESS 'measurement.read' URI 'c2004://measurement/sensors/query/read' MODE 'execute'",
      ].join('\n'),
      text: [
        'VERSION: 6',
        "EVENT 'frontend.ready':",
        "  RUN_URI 'c2004://measurement/sensors/query/read' MODE 'execute' PAYLOAD '{}'",
      ].join('\n'),
    });

    assert.equal(response?.status, 200);
    const body = response?.body as {
      ok: boolean;
      program: { processes: Record<string, unknown>; events: Record<string, unknown> };
    };
    assert.equal(body.ok, true);
    assert.ok(body.program.processes['measurement.read']);
    assert.ok(body.program.events['frontend.ready']);
  });

  it('migrates scenario-builder output to valid V6 before returning it', async () => {
    const built = await handleRequest('POST', '/api/oql/scenario-build', {
      source: 'test',
      data: {
        name: 'Pressure test',
        activities: [{ name: 'Pressure', criteria: { min: 10, max: 20, unit: 'bar' } }],
      },
    });
    const dsl = (built?.body as { dsl: string }).dsl;
    assert.match(dsl, /^VERSION: 6/m);
    assert.match(dsl, /^TEST_STEP:$/m);

    const parsed = await handleRequest('POST', '/api/oql/parse', { text: dsl });
    assert.equal((parsed?.body as { ok: boolean; errors: string[] }).ok, true);
  });

  it('migrates serialized compatibility AST output to valid V6', async () => {
    const serialized = await handleRequest('POST', '/api/oql/serialize', {
      ast: {
        scenario: 'Serialized',
        goals: [{
          name: 'Prepare',
          tasks: [],
          conditions: [],
          steps: [{ type: 'set', parameter: 'pump', value: 'off' }],
        }],
        funcs: [],
      },
    });
    const text = (serialized?.body as { text: string }).text;
    assert.match(text, /^VERSION: 6/m);
    const parsed = await handleRequest('POST', '/api/oql/parse', { text });
    assert.equal((parsed?.body as { ok: boolean }).ok, true);
  });
});

describe('oql-runtime-server HTTP', () => {
  let server: http.Server;
  let baseUrl = '';

  before(async () => {
    server = http.createServer(async (req, res) => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1');
      const body =
        req.method === 'POST'
          ? await new Promise<Record<string, unknown>>((resolve, reject) => {
              const chunks: Buffer[] = [];
              req.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
              req.on('end', () => resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}));
              req.on('error', reject);
            })
          : {};
      const handled = await handleRequest(req.method ?? 'GET', url.pathname, body);
      const payload = JSON.stringify(handled?.body ?? { error: 'not found' });
      res.writeHead(handled?.status ?? 404, { 'Content-Type': 'application/json' });
      res.end(payload);
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const addr = server.address();
    if (!addr || typeof addr === 'string') throw new Error('no address');
    baseUrl = `http://127.0.0.1:${addr.port}`;
  });

  after(async () => {
    server.close();
    await once(server, 'close');
  });

  it('quote endpoint matches Python contract shape', async () => {
    const res = await request(baseUrl, 'POST', '/api/oql/quote', { value: 'hello' });
    assert.equal(res.status, 200);
    assert.equal(res.json.quoted, "'hello'");
  });

  it('rejects the removed legacy API prefix', async () => {
    const res = await request(baseUrl, 'POST', '/api/cql/quote', { value: 'legacy' });
    assert.equal(res.status, 404);
    assert.equal(res.json.error, 'not found');
  });
});
