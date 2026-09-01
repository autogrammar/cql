import {
  OQL_MIGRATION_INPUT_VERSIONS,
  RUNTIME_OQL_VERSION,
} from '@semcod/oqlts';
import { OQL_POST_HANDLERS } from './oql-route-handlers.ts';

const VERSION = '0.1.0';
const OQL_API_PREFIX = '/api/oql/';

export type JsonBody = Record<string, unknown>;

export function readJsonBody(req: import('node:http').IncomingMessage): Promise<JsonBody> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on('data', (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8').trim();
      if (!raw) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw) as JsonBody);
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

export function jsonResponse(res: import('node:http').ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

export async function handleRequest(
  method: string,
  pathname: string,
  body: JsonBody,
): Promise<{ status: number; body: unknown } | null> {
  if (method === 'GET' && pathname === '/health') {
    return { status: 200, body: { status: 'ok', service: 'oql-runtime-server', version: VERSION } };
  }

  if (method === 'GET' && pathname === '/api/oql/capabilities') {
    return {
      status: 200,
      body: {
        runtime: 'node',
        package: '@oqlos/cql-runtime',
        runtime_oql_version: RUNTIME_OQL_VERSION,
        accepted_oql_versions: [RUNTIME_OQL_VERSION],
        migration_input_versions: [...OQL_MIGRATION_INPUT_VERSIONS],
        canonical_prefix: OQL_API_PREFIX,
        implemented: Object.keys(OQL_POST_HANDLERS),
        stubbed_501: [],
      },
    };
  }

  if (method !== 'POST' || !pathname.startsWith(OQL_API_PREFIX)) {
    return null;
  }

  const handler = OQL_POST_HANDLERS[pathname];
  return handler ? handler(body) : null;
}
