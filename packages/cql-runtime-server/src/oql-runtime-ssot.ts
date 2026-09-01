/**
 * Runtime OQL v6 SSOT via @semcod/oqlts — mirrors c2004 oql_*_ssot.py adapters.
 *
 * The parser package may understand older documents so the migration tooling can
 * read them. The runtime boundary is deliberately narrower: only VERSION: 6 may
 * be parsed, validated or executed here.
 */
import { parseOql, runtimeOqlVersionIssue, validateOql } from '@semcod/oqlts';
import type { OqlParseResult } from '@semcod/oqlts';
import { cmdToSteps, type LegacyStep } from './oql-cmd-steps.ts';

export function runtimeOqlVersionError(text: string): string | null {
  return runtimeOqlVersionIssue(text)?.message ?? null;
}

export type LegacyGoal = {
  name: string;
  tasks: unknown[];
  conditions: unknown[];
  steps: LegacyStep[];
};
export type LegacyAst = {
  scenario: string;
  goals: LegacyGoal[];
  funcs: unknown[];
};

export function tsParseToAst(payload: OqlParseResult): LegacyAst {
  const scenario = payload.scenario ?? { goals: [], meta: {} };
  const meta = scenario.meta ?? {};
  const title = String(scenario.title ?? meta.scenario ?? 'OQL Scenario');
  const goals: LegacyGoal[] = [];

  for (const goal of scenario.goals ?? []) {
    const uiGoal: LegacyGoal = { name: String(goal.name ?? ''), tasks: [], conditions: [], steps: [] };
    for (const cmd of goal.steps ?? []) {
      for (const step of cmdToSteps(cmd)) {
        uiGoal.steps.push(step);
      }
    }
    goals.push(uiGoal);
  }

  return { scenario: title, goals, funcs: [] };
}

function formatIssue(issue: { line?: number; message?: string }): string {
  const message = issue.message == null ? '' : String(issue.message);
  return issue.line != null ? `Linia ${issue.line}: ${message}` : message;
}

export function parseDslSsot(text: string): { ok: boolean; errors: string[]; ast: LegacyAst | null } {
  const versionError = runtimeOqlVersionError(text);
  if (versionError) return { ok: false, errors: [versionError], ast: null };
  const payload = parseOql(text);
  const errors = (payload.errors ?? []).map((issue) => formatIssue(issue));
  if (errors.length) {
    return { ok: false, errors, ast: null };
  }
  const ast = tsParseToAst(payload);
  return { ok: ast.goals.length > 0, errors: [], ast };
}

export function validateDslSsot(text: string): {
  ok: boolean;
  errors: string[];
  warnings: string[];
  violations: unknown[];
  fixedText: string | null;
} {
  const versionError = runtimeOqlVersionError(text);
  if (versionError) {
    return {
      ok: false,
      errors: [versionError],
      warnings: [],
      violations: [],
      fixedText: null,
    };
  }
  const payload = validateOql(text);
  const errors = (payload.errors ?? []).map((issue) => formatIssue(issue));
  const warnings = (payload.warnings ?? []).map((issue) => formatIssue(issue));
  return {
    ok: Boolean(payload.valid) && errors.length === 0,
    errors,
    warnings,
    violations: [],
    fixedText: null,
  };
}
