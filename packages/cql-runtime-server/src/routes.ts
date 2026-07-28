import {
  compileOqlHuiProgram,
  migrateOqlToV6,
} from '@oqlos/cql-runtime';
import {
  applyMappingToExecPlan,
  resolveFuncSteps,
  resolveTaskMapping,
} from '@oqlos/cql-runtime/mapping';
import { DslScenarioBuilders } from '@oqlos/cql-runtime/scenario-builders';
import { executeDsl } from '@oqlos/cql-runtime/exec';
import {
  canonicalizeDslQuotes,
  formatDslLiteral,
  normalizeDslTextQuotes,
  quoteDslValue,
  readQuotedToken,
} from '@oqlos/cql-runtime/quotes';
import { highlightDsl } from '@oqlos/cql-runtime/highlight';
import { astToDslText } from '@oqlos/cql-runtime/serialize';
import {
  parseDslSsot,
  runtimeOqlVersionError,
  validateDslSsot,
} from './oql-runtime-ssot.ts';
import {
  collectOqlGrants,
  canEditOqlLine,
  canReadOqlLine,
  isOqlGrantLine,
  OQL_MIGRATION_INPUT_VERSIONS,
  oqlLineTarget,
  RUNTIME_OQL_VERSION,
} from '@semcod/oqlts';

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
        implemented: [
          '/api/oql/quote',
          '/api/oql/unquote',
          '/api/oql/format-literal',
          '/api/oql/canonicalize',
          '/api/oql/normalize',
          '/api/oql/highlight',
          '/api/oql/parse',
          '/api/oql/serialize',
          '/api/oql/validate',
          '/api/oql/exec',
          '/api/oql/compile-hui',
          '/api/oql/access-check',
          '/api/oql/read-projection',
          '/api/oql/scenario-build',
          '/api/oql/resolve-task',
          '/api/oql/resolve-func',
          '/api/oql/exec-mapped',
        ],
        stubbed_501: [],
      },
    };
  }

  if (method !== 'POST' || !pathname.startsWith(OQL_API_PREFIX)) {
    return null;
  }

  const text = String(body.text ?? '');

  switch (pathname) {
    case '/api/oql/quote':
      return { status: 200, body: { quoted: quoteDslValue(body.value) } };
    case '/api/oql/unquote':
      return { status: 200, body: readQuotedToken(String(body.token ?? '')) };
    case '/api/oql/format-literal':
      return { status: 200, body: { literal: formatDslLiteral(String(body.value ?? '')) } };
    case '/api/oql/canonicalize':
      return { status: 200, body: { text: canonicalizeDslQuotes(text) } };
    case '/api/oql/normalize':
      return { status: 200, body: { text: normalizeDslTextQuotes(text) } };
    case '/api/oql/highlight': {
      if (body.mode === 'tokens') {
        return {
          status: 501,
          body: {
            detail: {
              message: 'Token-stream highlight output is not implemented in Node runtime server.',
              ts_reference: 'oqlos/cql/runtime/dsl.highlight.ts',
            },
          },
        };
      }
      return { status: 200, body: { html: highlightDsl(text) } };
    }
    case '/api/oql/parse': {
      const ssot = parseDslSsot(text);
      return { status: 200, body: { ok: ssot.ok, errors: ssot.errors, ast: ssot.ast } };
    }
    case '/api/oql/serialize':
      return { status: 200, body: { text: migrateOqlToV6(astToDslText(body.ast as never)) } };
    case '/api/oql/validate': {
      const ssot = validateDslSsot(text);
      return {
        status: 200,
        body: {
          ok: ssot.ok,
          errors: ssot.errors,
          warnings: ssot.warnings,
          violations: ssot.violations,
          fixedText: ssot.fixedText,
        },
      };
    }
    case '/api/oql/exec': {
      // Parse the one runtime language via @semcod/oqlts, then execute the
      // adapted AST with the shared executor — composition, no duplicate grammar.
      const ssot = parseDslSsot(text);
      if (!ssot.ok) {
        return { status: 200, body: { ok: false, errors: ssot.errors, ast: ssot.ast, plan: [] } };
      }
      const result = executeDsl(ssot.ast as never, body.context as never);
      return {
        status: 200,
        body: { ok: result.ok, errors: result.errors, ast: result.ast ?? ssot.ast, plan: result.plan },
      };
    }
    case '/api/oql/compile-hui': {
      const systemText = String(body.system_text ?? body.systemText ?? '');
      const versionErrors = [
        runtimeOqlVersionError(text),
        ...(systemText ? [runtimeOqlVersionError(systemText)] : []),
      ].filter((error): error is string => Boolean(error));
      if (versionErrors.length) {
        return { status: 200, body: { ok: false, program: null, errors: versionErrors, warnings: [] } };
      }
      const program = compileOqlHuiProgram(text, { systemText });
      return {
        status: 200,
        body: {
          ok: program.errors.length === 0,
          program,
          errors: program.errors,
          warnings: program.warnings,
        },
      };
    }
    case '/api/oql/scenario-build': {
      const source = String(body.source ?? 'generic');
      const data = (body.data ?? {}) as Record<string, unknown>;
      if (source === 'test') {
        const dsl = migrateOqlToV6(DslScenarioBuilders.buildDslFromTestScenario(data));
        return {
          status: 200,
          body: {
            dsl,
            goals: DslScenarioBuilders.buildGoalsFromTestScenario(data),
          },
        };
      }
      return {
        status: 200,
        body: { dsl: migrateOqlToV6(DslScenarioBuilders.buildDslFromGenericScenario(data)) },
      };
    }
    case '/api/oql/resolve-task': {
      const hardwareMap = (body.hardware_map ?? body.hardwareMap ?? {}) as Record<string, unknown>;
      const task = (body.task ?? {}) as Record<string, unknown>;
      const resolved = resolveTaskMapping(hardwareMap, task, {
        environment: (body.environment as string | null | undefined) ?? null,
        usageMode: (body.usage_mode as string | null | undefined) ?? (body.usageMode as string | null | undefined) ?? null,
      });
      return { status: resolved.ok ? 200 : 400, body: resolved };
    }
    case '/api/oql/resolve-func': {
      const hardwareMap = (body.hardware_map ?? body.hardwareMap ?? {}) as Record<string, unknown>;
      const funcName = String(body.func_name ?? body.funcName ?? '');
      const result = resolveFuncSteps(hardwareMap, funcName, {
        environment: (body.environment as string | null | undefined) ?? null,
        usageMode: (body.usage_mode as string | null | undefined) ?? (body.usageMode as string | null | undefined) ?? null,
      });
      return { status: result.ok === false ? 400 : 200, body: result };
    }
    case '/api/oql/access-check': {
      // Server-side ACCESS: given the OLD scenario's inline ALLOW/DENY grants,
      // is `role` allowed to turn old_text into new_text? Mirrors the editor's
      // per-line lock — the single grant engine (@semcod/oqlts) is the authority.
      const oldText = String(body.old_text ?? body.oldText ?? '');
      const newText = String(body.new_text ?? body.newText ?? text);
      const role = String(body.role ?? '');
      const grants = collectOqlGrants(oldText);
      const oldLines = oldText.split('\n');
      const newLines = newText.split('\n');
      const lockedIdx: number[] = [];
      oldLines.forEach((line, i) => {
        if (oqlLineTarget(line) && !canEditOqlLine(role, line, grants)) lockedIdx.push(i);
      });
      if (lockedIdx.length === 0) {
        return { status: 200, body: { allowed: true, violations: [] } };
      }
      if (newLines.length !== oldLines.length) {
        return { status: 200, body: { allowed: false, violations: [{ reason: 'line-count-changed-with-locks' }] } };
      }
      const violations = lockedIdx
        .filter((i) => newLines[i] !== oldLines[i])
        .map((i) => ({ line: i + 1, text: oldLines[i] }));
      return { status: 200, body: { allowed: violations.length === 0, violations } };
    }
    case '/api/oql/read-projection': {
      // Produce the only source projection that may be returned to an editor or
      // browser runtime. Policy declarations are system-only; ordinary OQL
      // lines follow DENY ... READ grants from the complete composed program.
      const role = String(body.role ?? '').trim().toLowerCase() || 'operator';
      const policyText = String(body.policy_text ?? body.policyText ?? text);
      const grants = collectOqlGrants(policyText);
      const rawDocuments = Array.isArray(body.documents)
        ? body.documents
        : [{ id: 'document', text }];

      const documents = rawDocuments.map((raw, documentIndex) => {
        const document = (raw ?? {}) as Record<string, unknown>;
        const id = String(document.id ?? `document-${documentIndex}`);
        const source = String(document.text ?? '');
        if (role === 'system' || role === 'sys' || role === 'root' || role === 'superuser') {
          return { id, text: source, hidden_lines: 0 };
        }

        let hiddenLines = 0;
        const projected = source
          .split('\n')
          .filter((line) => {
            // DISALLOW is reserved syntax requested by the system policy. It is
            // hidden even before its parser semantics are introduced.
            const policyDeclaration = isOqlGrantLine(line) || /^\s*DISALLOW\b/i.test(line);
            const readable = !policyDeclaration && canReadOqlLine(role, line, grants);
            if (!readable) hiddenLines += 1;
            return readable;
          })
          .join('\n');
        return { id, text: projected, hidden_lines: hiddenLines };
      });

      return {
        status: 200,
        body: {
          role,
          policy_declarations_hidden: !(role === 'system' || role === 'sys' || role === 'root' || role === 'superuser'),
          documents,
        },
      };
    }
    case '/api/oql/exec-mapped': {
      const ssot = parseDslSsot(text);
      if (!ssot.ok) {
        return {
          status: 200,
          body: { ok: false, errors: ssot.errors, ast: ssot.ast, plan: [], mappedPlan: [] },
        };
      }
      const hardwareMap = (body.hardware_map ?? body.hardwareMap ?? {}) as Record<string, unknown>;
      const environment = (body.environment as string | null | undefined) ?? null;
      const usageMode = (body.usage_mode as string | null | undefined)
        ?? (body.usageMode as string | null | undefined)
        ?? null;
      const result = executeDsl(ssot.ast as never, body.context as never);
      const mappedPlan = applyMappingToExecPlan(result.plan ?? [], hardwareMap, { environment, usageMode });
      return {
        status: 200,
        body: {
          ok: result.ok,
          errors: result.errors,
          ast: result.ast ?? null,
          plan: result.plan,
          mappedPlan,
        },
      };
    }
    default:
      return null;
  }
}
