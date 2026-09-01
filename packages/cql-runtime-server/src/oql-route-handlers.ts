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
  collectOqlGrants,
  canEditOqlLine,
  canReadOqlLine,
  isOqlGrantLine,
  oqlLineTarget,
} from '@semcod/oqlts';
import {
  parseDslSsot,
  runtimeOqlVersionError,
  validateDslSsot,
} from './oql-runtime-ssot.ts';
import type { JsonBody } from './routes.ts';

type RouteResult = { status: number; body: unknown };

function readBodyText(body: JsonBody): string {
  return String(body.text ?? '');
}

function readHardwareMap(body: JsonBody): Record<string, unknown> {
  return (body.hardware_map ?? body.hardwareMap ?? {}) as Record<string, unknown>;
}

function readUsageMode(body: JsonBody): string | null {
  return (body.usage_mode as string | null | undefined)
    ?? (body.usageMode as string | null | undefined)
    ?? null;
}

function handleQuote(body: JsonBody): RouteResult {
  return { status: 200, body: { quoted: quoteDslValue(body.value) } };
}

function handleUnquote(body: JsonBody): RouteResult {
  return { status: 200, body: readQuotedToken(String(body.token ?? '')) };
}

function handleFormatLiteral(body: JsonBody): RouteResult {
  return { status: 200, body: { literal: formatDslLiteral(String(body.value ?? '')) } };
}

function handleCanonicalize(body: JsonBody): RouteResult {
  return { status: 200, body: { text: canonicalizeDslQuotes(readBodyText(body)) } };
}

function handleNormalize(body: JsonBody): RouteResult {
  return { status: 200, body: { text: normalizeDslTextQuotes(readBodyText(body)) } };
}

function handleHighlight(body: JsonBody): RouteResult {
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
  return { status: 200, body: { html: highlightDsl(readBodyText(body)) } };
}

function handleParse(body: JsonBody): RouteResult {
  const ssot = parseDslSsot(readBodyText(body));
  return { status: 200, body: { ok: ssot.ok, errors: ssot.errors, ast: ssot.ast } };
}

function handleSerialize(body: JsonBody): RouteResult {
  return { status: 200, body: { text: migrateOqlToV6(astToDslText(body.ast as never)) } };
}

function handleValidate(body: JsonBody): RouteResult {
  const ssot = validateDslSsot(readBodyText(body));
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

function handleExec(body: JsonBody): RouteResult {
  const text = readBodyText(body);
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

function handleCompileHui(body: JsonBody): RouteResult {
  const text = readBodyText(body);
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

function handleScenarioBuild(body: JsonBody): RouteResult {
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

function handleResolveTask(body: JsonBody): RouteResult {
  const hardwareMap = readHardwareMap(body);
  const task = (body.task ?? {}) as Record<string, unknown>;
  const resolved = resolveTaskMapping(hardwareMap, task, {
    environment: (body.environment as string | null | undefined) ?? null,
    usageMode: readUsageMode(body),
  });
  return { status: resolved.ok ? 200 : 400, body: resolved };
}

function handleResolveFunc(body: JsonBody): RouteResult {
  const hardwareMap = readHardwareMap(body);
  const funcName = String(body.func_name ?? body.funcName ?? '');
  const result = resolveFuncSteps(hardwareMap, funcName, {
    environment: (body.environment as string | null | undefined) ?? null,
    usageMode: readUsageMode(body),
  });
  return { status: result.ok === false ? 400 : 200, body: result };
}

function handleAccessCheck(body: JsonBody): RouteResult {
  const oldText = String(body.old_text ?? body.oldText ?? '');
  const newText = String(body.new_text ?? body.newText ?? readBodyText(body));
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

function isSystemRole(role: string): boolean {
  return role === 'system' || role === 'sys' || role === 'root' || role === 'superuser';
}

function handleReadProjection(body: JsonBody): RouteResult {
  const role = String(body.role ?? '').trim().toLowerCase() || 'operator';
  const policyText = String(body.policy_text ?? body.policyText ?? readBodyText(body));
  const grants = collectOqlGrants(policyText);
  const rawDocuments = Array.isArray(body.documents)
    ? body.documents
    : [{ id: 'document', text: readBodyText(body) }];

  const documents = rawDocuments.map((raw, documentIndex) => {
    const document = (raw ?? {}) as Record<string, unknown>;
    const id = String(document.id ?? `document-${documentIndex}`);
    const source = String(document.text ?? '');
    if (isSystemRole(role)) {
      return { id, text: source, hidden_lines: 0 };
    }

    let hiddenLines = 0;
    const projected = source
      .split('\n')
      .filter((line) => {
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
      policy_declarations_hidden: !isSystemRole(role),
      documents,
    },
  };
}

function handleExecMapped(body: JsonBody): RouteResult {
  const text = readBodyText(body);
  const ssot = parseDslSsot(text);
  if (!ssot.ok) {
    return {
      status: 200,
      body: { ok: false, errors: ssot.errors, ast: ssot.ast, plan: [], mappedPlan: [] },
    };
  }
  const hardwareMap = readHardwareMap(body);
  const environment = (body.environment as string | null | undefined) ?? null;
  const usageMode = readUsageMode(body);
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

export const OQL_POST_HANDLERS: Record<string, (body: JsonBody) => RouteResult> = {
  '/api/oql/quote': handleQuote,
  '/api/oql/unquote': handleUnquote,
  '/api/oql/format-literal': handleFormatLiteral,
  '/api/oql/canonicalize': handleCanonicalize,
  '/api/oql/normalize': handleNormalize,
  '/api/oql/highlight': handleHighlight,
  '/api/oql/parse': handleParse,
  '/api/oql/serialize': handleSerialize,
  '/api/oql/validate': handleValidate,
  '/api/oql/exec': handleExec,
  '/api/oql/compile-hui': handleCompileHui,
  '/api/oql/scenario-build': handleScenarioBuild,
  '/api/oql/resolve-task': handleResolveTask,
  '/api/oql/resolve-func': handleResolveFunc,
  '/api/oql/access-check': handleAccessCheck,
  '/api/oql/read-projection': handleReadProjection,
  '/api/oql/exec-mapped': handleExecMapped,
};
