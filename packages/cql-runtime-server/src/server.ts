import http from 'node:http';

import { handleRequest, jsonResponse, readJsonBody } from './routes.ts';

const host = process.env.OQL_RUNTIME_HOST ?? '0.0.0.0';
const port = Number(process.env.OQL_RUNTIME_PORT ?? 8101);

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`);
  const method = req.method ?? 'GET';

  try {
    const body = method === 'POST' ? await readJsonBody(req) : {};
    const handled = await handleRequest(method, url.pathname, body);
    if (!handled) {
      jsonResponse(res, 404, { error: 'not found', path: url.pathname });
      return;
    }
    jsonResponse(res, handled.status, handled.body);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    jsonResponse(res, 400, { error: 'bad request', detail: message });
  }
});

server.listen(port, host, () => {
  // eslint-disable-next-line no-console
  console.log(`oql-runtime-server listening on http://${host}:${port}`);
});
