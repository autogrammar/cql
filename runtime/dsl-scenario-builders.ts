// frontend/src/components/dsl/dsl-scenario-builders.ts
// DSL builders for different scenario types (moved from modules)
import { renderLegacyTaskAsDslLines } from './dsl-content-helpers';
import { quoteDslValue as q } from './dsl.quotes';

function criteriaDslLines(c: any, param: string, unit: string): string[] {
  const lines: string[] = [];
  if (typeof c.min !== 'undefined') lines.push(`  IF ${q(param)} >= ${q(`${c.min}${unit ? ` ${unit}` : ''}`)}`);
  if (typeof c.max !== 'undefined') lines.push(`  IF ${q(param)} <= ${q(`${c.max}${unit ? ` ${unit}` : ''}`)}`);
  if (typeof c.targetValue !== 'undefined') lines.push(`  IF ${q(param)} = ${q(`${c.targetValue}${unit ? ` ${unit}` : ''}`)}`);
  if (typeof c.duration !== 'undefined') lines.push(`  IF ${q('czas')} >= ${q(`${c.duration} s`)}`);
  return lines;
}

function criteriaGoalConditions(c: any, param: string, unit: string): any[] {
  const result = 'test zaliczony';
  const conditions: any[] = [];
  if (typeof c.min !== 'undefined') conditions.push({ type: 'if', parameter: param, operator: '>=', value: String(c.min), unit, result });
  if (typeof c.max !== 'undefined') conditions.push({ type: 'if', parameter: param, operator: '<=', value: String(c.max), unit, result });
  if (typeof c.targetValue !== 'undefined') conditions.push({ type: 'if', parameter: param, operator: '=', value: String(c.targetValue), unit, result });
  if (typeof c.duration !== 'undefined') conditions.push({ type: 'if', parameter: 'czas', operator: '>=', value: String(c.duration), unit: 's', result });
  return conditions;
}

function variableDslLine(v: any): string | null {
  const action = String(v?.action || 'GET').toUpperCase();
  const param = String(v?.parameter || '');
  const val = String(v?.value ?? '').trim();
  const unit = String(v?.unit || '').trim();
  if (!param) return null;
  if (action === 'GET' || action === 'VAL') {
    return `  ${action} ${q(param)}${unit ? ` ${q(unit)}` : ''}`;
  }
  const right = unit ? `${val} ${unit}` : `${val}`;
  return `  ${action} ${q(param)} ${q(right)}`;
}

function conditionDslLine(c: any): string | null {
  const t = (c?.type || '').toLowerCase();
  if (t === 'if') {
    const unit = (c?.unit || '').trim();
    const val = String(c?.value ?? '').trim();
    return `  IF ${q(c?.parameter || '')} ${c?.operator || '='} ${q(`${val}${unit ? ` ${unit}` : ''}`)}`;
  }
  if (t === 'else') {
    return `  ELSE ${c?.actionType || 'ERROR'} ${q(c?.actionMessage || '')}`;
  }
  return null;
}

function goalDslLines(goal: any): string[] {
  const lines: string[] = [];
  lines.push(`GOAL: ${goal.name || 'GOAL'}`);

  for (const task of Array.isArray(goal?.tasks) ? goal.tasks : []) {
    if (task?.function && task?.object) {
      lines.push(...renderLegacyTaskAsDslLines(task, '  '));
    }
  }

  for (const varGroup of Array.isArray(goal?.variables) ? goal.variables : []) {
    for (const v of Array.isArray(varGroup?.variables) ? varGroup.variables : []) {
      const line = variableDslLine(v);
      if (line) lines.push(line);
    }
  }

  for (const c of Array.isArray(goal?.conditions) ? goal.conditions : []) {
    const line = conditionDslLine(c);
    if (line) lines.push(line);
  }

  lines.push('');
  return lines;
}

/**
 * Build DSL from TestScenario for device testing
 */
export class DslScenarioBuilders {
  /**
   * Build DSL text from TestScenario (moved from device-testing.dsl.ts)
   */
  static buildDslFromTestScenario(sc: any): string {
    const lines: string[] = [];
    lines.push(`SCENARIO: ${sc.name}`);
    lines.push('');
    for (const act of (sc.activities || [])) {
      lines.push(`GOAL: ${act.name}`);
      lines.push(`  SET ${q(act.name)} ${q('1')}`);
      const c: any = act.criteria || {};
      const unit = c.unit || '';
      const param = unit ? unit : act.name;
      lines.push(...criteriaDslLines(c, param, unit));
      lines.push('');
    }
    return lines.join('\n');
  }

  /**
   * Build goals JSON from TestScenario (moved from device-testing.dsl.ts)
   */
  static buildGoalsFromTestScenario(sc: any): any[] {
    const goals: any[] = [];
    for (const act of (sc.activities || [])) {
      const c: any = act.criteria || {};
      const unit = c.unit || '';
      const param = unit ? unit : act.name;
      goals.push({
        name: act.name,
        tasks: [{ function: 'Sprawdź', object: act.name }],
        conditions: criteriaGoalConditions(c, param, unit),
      });
    }
    return goals;
  }

  /**
   * Build DSL from generic scenario content
   */
  static buildDslFromGenericScenario(scenario: any): string {
    const lines: string[] = [];
    const name = scenario?.name || 'Generic Scenario';
    lines.push(`SCENARIO: ${name}`);
    lines.push('');

    const goals = Array.isArray(scenario?.goals) ? scenario.goals : [];
    for (const goal of goals) {
      lines.push(...goalDslLines(goal));
    }

    return lines.join('\n');
  }
}
