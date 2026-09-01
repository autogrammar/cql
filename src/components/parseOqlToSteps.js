/**
 * parseOqlToSteps.js
 * Parses OQL scenario code into structured goals/steps for the graphical renderer.
 * Primary path: @semcod/oqlts parseOql → oqlAstToSteps (single source of truth).
 * Legacy regex fallback for pre-v5 / extended syntax (ASSERT, API, …).
 */

import { parseOql } from '@semcod/oqlts';
import { astToSteps, finalizeGoal, applyGoalMeta } from './oqlAstToSteps.js';

/**
 * Parse an OQL scenario string into a structured object.
 * @param {string} code - Raw OQL scenario code
 * @returns {{ scenarioName: string, deviceType: string, deviceModel: string, manufacturer: string, goals: Array<Goal> }}
 */
function _applyHeaderLine(result, line) {
  const scenarioMatch = line.match(/^SCENARIO:\s*['"]([^'"]+)['"]/);
  if (scenarioMatch) { result.scenarioName = scenarioMatch[1]; return true; }

  const dtMatch = line.match(/^DEVICE_TYPE:\s*['"]([^'"]+)['"]/);
  if (dtMatch) { result.deviceType = dtMatch[1]; return true; }

  const dmMatch = line.match(/^DEVICE_MODEL:\s*['"]([^'"]+)['"]/);
  if (dmMatch) { result.deviceModel = dmMatch[1]; return true; }

  const mfMatch = line.match(/^MANUFACTURER:\s*['"]([^'"]+)['"]/);
  if (mfMatch) { result.manufacturer = mfMatch[1]; return true; }

  return false;
}

function _applyCommentLine(currentGoal, currentFunc, line) {
  const comment = { type: 'COMMENT', raw: line, text: line.replace(/^#\s*/, '') };
  if (currentGoal) {
    currentGoal.steps.push(comment);
  } else if (currentFunc) {
    currentFunc.steps.push(comment);
  }
}

function _startFunc(result, line) {
  const match = line.match(/^FUNC:\s*(.*)/);
  if (!match) return null;
  const func = { name: (match[1] || '').trim(), steps: [] };
  result.funcs.push(func);
  return func;
}

function _startGoal(result, line) {
  const match = line.match(/^GOAL:\s*(.*)/);
  if (!match) return null;
  const goal = { name: (match[1] || '').trim(), steps: [] };
  result.goals.push(goal);
  return goal;
}

function _applyGoalMeta(currentGoal, step) {
  applyGoalMeta(currentGoal, step);
}

function _applyFuncStep(currentFunc, line) {
  const step = parseStep(line);
  if (!step) return;
  if (step.type === 'SET' && step._goalMeta === 'NAME') {
    currentFunc.name = step.value;
    return;
  }
  currentFunc.steps.push(step);
}

function _attachMessageToPrevious(currentGoal, step) {
  const prev = currentGoal.steps[currentGoal.steps.length - 1];
  if (prev.type !== 'CHECK' && prev.type !== 'IF') return false;
  if (step.type === 'CORRECT' || step.type === 'PASS') {
    prev.correctMsg = step.message;
  } else {
    prev.errorMsg = step.message;
  }
  return true;
}

function _applyGoalStep(currentGoal, line) {
  const step = parseStep(line);
  if (!step) return;

  if (step.type === 'SET' && step._goalMeta) {
    _applyGoalMeta(currentGoal, step);
    return;
  }

  if ((step.type === 'CORRECT' || step.type === 'ERROR') && currentGoal.steps.length > 0) {
    if (_attachMessageToPrevious(currentGoal, step)) return;
  }

  if ((step.type === 'PASS' || step.type === 'FAIL') && !step.parameter && currentGoal.steps.length > 0) {
    if (_attachMessageToPrevious(currentGoal, step)) return;
  }

  currentGoal.steps.push(step);
}

function _finalizeGoal(goal) {
  finalizeGoal(goal);
}

function parseOqlToStepsLegacy(code) {
  const lines = (code || '').split('\n');
  const result = {
    scenarioName: '',
    deviceType: '',
    deviceModel: '',
    manufacturer: '',
    goals: [],
    funcs: [],
  };

  let currentGoal = null;
  let currentFunc = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) continue;

    if (_applyHeaderLine(result, line)) continue;

    if (line.startsWith('#')) {
      _applyCommentLine(currentGoal, currentFunc, line);
      continue;
    }

    const nextFunc = _startFunc(result, line);
    if (nextFunc) {
      currentGoal = null;
      currentFunc = nextFunc;
      continue;
    }

    const nextGoal = _startGoal(result, line);
    if (nextGoal) {
      currentFunc = null;
      currentGoal = nextGoal;
      continue;
    }

    if (currentFunc) {
      _applyFuncStep(currentFunc, line);
      continue;
    }

    if (currentGoal) {
      _applyGoalStep(currentGoal, line);
    }
  }

  for (const goal of result.goals) {
    _finalizeGoal(goal);
  }

  return result;
}

/** Parse OQL via @semcod/oqlts; legacy regex fallback on parse errors. */
export function parseOqlToSteps(code) {
  const parsed = parseOql(code || '');
  if (parsed.errors.length === 0) {
    return astToSteps(parsed);
  }
  return parseOqlToStepsLegacy(code);
}

function _matchFirst(line, patterns) {
  for (const re of patterns) {
    const m = line.match(re);
    if (m) return m;
  }
  return null;
}

function _parseSetMeta(line, meta) {
  const patterns = {
    NAME: [/^SET\s+NAME\s+'([^']+)'/],
    VAL: [/^SET\s+VAL\s+'([^']+)'/, /^SET\s+VAL\s+(\S+)/],
    MIN: [/^SET\s+MIN\s+'([^']+)'/, /^SET\s+MIN\s+(.+)/],
    MAX: [/^SET\s+MAX\s+'([^']+)'/, /^SET\s+MAX\s+(.+)/],
  };
  const m = _matchFirst(line, patterns[meta]);
  if (!m) return null;
  if (meta === 'NAME') return { type: 'SET', raw: line, _goalMeta: meta, value: m[1] };
  if (meta === 'VAL') return { type: 'SET', raw: line, _goalMeta: meta, parameter: m[1] };
  const { value, unit } = splitValueUnit(m[1].trim());
  return { type: 'SET', raw: line, _goalMeta: meta, value, unit };
}

function _parseSetQuoted(line, quote) {
  const re = quote === "'" ? /^SET\s+'([^']+)'\s+'([^']+)'/ : /^SET\s+"([^"]+)"\s+"([^"]+)"/;
  const m = line.match(re);
  if (!m) return null;
  const { value, unit } = splitValueUnit(m[2]);
  return { type: 'SET', raw: line, parameter: m[1], value, unit };
}

function _parseQuotedMessage(line, prefix, type) {
  const reSingle = new RegExp(`^${prefix}\\s+'([^']+)'`);
  const reDouble = new RegExp(`^${prefix}\\s+"([^"]+)"`);
  const m = line.match(reSingle) || line.match(reDouble);
  return m ? { type, raw: line, message: m[1] } : null;
}

function _parseLegacyBound(line, prefix, bound) {
  const re = new RegExp(`^${prefix}\\s+'([^']+)'\\s+'([^']+)'`);
  const m = line.match(re);
  if (!m) return null;
  const { value, unit } = splitValueUnit(m[2]);
  return { type: 'CHECK', raw: line, parameter: m[1], [bound]: value, unit, _legacy: prefix };
}

function _normalizeOperator(op) {
  return op === '≥' ? '>=' : op === '≤' ? '<=' : op;
}

function parseSetNameStep(line) { return _parseSetMeta(line, 'NAME'); }
function parseSetValStep(line) { return _parseSetMeta(line, 'VAL'); }
function parseSetMinStep(line) { return _parseSetMeta(line, 'MIN'); }
function parseSetMaxStep(line) { return _parseSetMeta(line, 'MAX'); }
function parseSetQuotedStep(line) { return _parseSetQuoted(line, "'"); }
function parseSetDblQuotedStep(line) { return _parseSetQuoted(line, '"'); }

function parseWaitStep(line) {
  const m = line.match(/^(?:SET\s+(?:WAIT|['"]WAIT['"])|WAIT)\s+['"]([^'"]+)['"]/i);
  if (m) {
    const { value, unit } = splitValueUnit(m[1]);
    return { type: 'WAIT', raw: line, value, unit: unit || 'ms' };
  }
  const m2 = line.match(/^(?:SET\s+(?:WAIT|['"]WAIT['"])|WAIT)\s+(\d+)\s*(ms|s)?/i);
  return m2 ? { type: 'WAIT', raw: line, value: m2[1], unit: m2[2] || 'ms' } : null;
}

function parseSampleStep(line) {
  const m = _matchFirst(line, [
    /^SAMPLE\s+['"]([^'"]+)['"]\s+(START|STOP)(?:\s+['"]?([^'"]+)['"]?)?/i,
    /^SAMPLE\s+([^\s]+)\s+(START|STOP)(?:\s+([^\s]+))?/i,
  ]);
  return m ? {
    type: 'SAMPLE', raw: line, parameter: m[1], action: m[2].toUpperCase(), interval: m[3],
  } : null;
}

function parseFuncCallStep(line) {
  const m = line.match(/^FUNC\s+"([^"]+)"(.*)/) || line.match(/^FUNC\s+'([^']+)'(.*)/);
  if (!m) return null;
  const args = [];
  const argRe = /["']([^"']+)["']/g;
  let argMatch;
  while ((argMatch = argRe.exec(m[2] || '')) !== null) {
    args.push(argMatch[1]);
  }
  return { type: 'FUNC_CALL', raw: line, funcName: m[1], args };
}

function parseMotorMoveStep(line) {
  const m = line.match(/^(motor\d+|motor-tic249|tic249)\s+(left|right)\s+(\d+)\s*(?:steps?)?$/i);
  if (!m) return null;
  const direction = m[2].toLowerCase();
  return {
    type: 'TASK', raw: line,
    object: m[1].toLowerCase(), function: direction,
    args: { direction, steps: Number.parseInt(m[3], 10) },
  };
}

function parseIfNumericRangeStep(line) {
  const m = line.match(/^IF\s+(\w+)\s+([\-\d.]+)\s*\.\.\s*([\-\d.]+)\s*(.*)/);
  if (!m) return null;
  return {
    type: 'CHECK', raw: line, parameter: m[1],
    min: m[2], max: m[3], unit: (m[4] || '').trim() || undefined,
  };
}

function parseLegacyCheckStep(line) {
  const m = line.match(/^CHECK\s+([\-\d.]+)\s*<=\s*(\w+)\s*<=\s*([\-\d.]+)\s*(.*)/);
  if (!m) return null;
  return {
    type: 'CHECK', raw: line, parameter: m[2],
    min: m[1], max: m[3], unit: (m[4] || '').trim() || undefined,
  };
}

function parseLegacyMinStep(line) { return _parseLegacyBound(line, 'MIN', 'min'); }
function parseLegacyMaxStep(line) { return _parseLegacyBound(line, 'MAX', 'max'); }

function parsePassBoundStep(line) {
  const m = line.match(/^PASS\s+'([^']+)'\s+'([^']+)'\s*$/i);
  return m ? { type: 'PASS', raw: line, parameter: m[1], message: m[2] } : null;
}

function parseFailStep(line) {
  const bound = line.match(/^FAIL\s+'([^']+)'\s+'([^']+)'\s*(?:GOTO\s+'([^']+)'|RETRY\s+(\d+))?\s*$/i);
  if (bound) {
    return {
      type: 'FAIL', raw: line, parameter: bound[1], message: bound[2],
      goto: bound[3], retry: bound[4] ? Number.parseInt(bound[4], 10) : undefined,
    };
  }
  const unbound = line.match(/^FAIL\s+'([^']+)'\s*(?:GOTO\s+'([^']+)'|RETRY\s+(\d+))?\s*$/i);
  if (unbound) {
    return {
      type: 'FAIL', raw: line, message: unbound[1],
      goto: unbound[2], retry: unbound[3] ? Number.parseInt(unbound[3], 10) : undefined,
    };
  }
  return null;
}

function parsePassFailStep(line) {
  return parsePassBoundStep(line) || parseFailStep(line) || _parseQuotedMessage(line, 'PASS', 'PASS');
}

function parseTaskDialogStep(line) {
  const m = line.match(/^TASK\s+(TITLE|VAL|PASS|FAIL)\s+'([^']+)'\s*$/i);
  return m ? { type: 'TASK_DIALOG_LINE', field: m[1].toLowerCase(), value: m[2], raw: line } : null;
}

function parseLegacyValStep(line) {
  const m = line.match(/^VAL\s+'([^']+)'\s+'([^']+)'/);
  return m ? { type: 'SET', raw: line, _goalMeta: 'VAL', parameter: m[1], unit: m[2] } : null;
}

function parseLegacyIfElseStep(line) {
  const m = line.match(/^IF\s+'([^']+)'\s*([<>=!]+)\s*'([^']+)'\s+ELSE\s+(ERROR|CORRECT)\s+'([^']+)'/);
  if (!m) return null;
  return {
    type: 'CHECK', raw: line, parameter: m[1],
    condition: m[2], value: m[3],
    errorMsg: m[4] === 'ERROR' ? m[5] : undefined,
    correctMsg: m[4] === 'CORRECT' ? m[5] : undefined,
    _legacy: 'IF',
  };
}

function parseIfDeltaStep(line) {
  const m = line.match(/^IF_DELTA\s+['"]([^'"]+)['"]\s+['"]([^'"]+)['"]\s+['"]([^'"]+)['"]/i);
  if (!m) return null;
  const { value, unit } = splitValueUnit(m[3]);
  return { type: 'CHECK', raw: line, parameter: m[1], window: m[2], max: value, unit, _legacy: 'IF_DELTA' };
}

function parseIfComparisonStep(line) {
  const m = line.match(/^IF\s+['"]([^'"]+)['"]\s*(>=|<=|>|<|=|!=|≥|≤)\s*['"]?([^'"]+)['"]?/i);
  if (!m) return null;
  const { value, unit } = splitValueUnit(m[3]);
  return {
    type: 'CHECK', raw: line, parameter: m[1],
    condition: _normalizeOperator(m[2]), value, unit, _legacy: 'IF',
  };
}

function parseSaveStep(line) {
  const m = line.match(/^SAVE\s+'([^']+)'/);
  return m ? { type: 'SAVE', raw: line, parameter: m[1] } : null;
}

function parseLogStep(line) { return _parseQuotedMessage(line, 'LOG', 'LOG'); }
function parseCorrectStep(line) { return _parseQuotedMessage(line, 'CORRECT', 'CORRECT'); }
function parseErrorStep(line) { return _parseQuotedMessage(line, 'ERROR', 'ERROR'); }

function parseExpectStep(line) {
  return line.startsWith('EXPECT_') ? { type: 'EXPECT', raw: line } : null;
}

function parseApiStep(line) {
  const m = _matchFirst(line, [
    /^API[_ ](GET|POST|PUT|DELETE)\s+"([^"]+)"/,
    /^API[_ ](GET|POST|PUT|DELETE)\s+'([^']+)'/,
  ]);
  return m ? { type: 'API', raw: line, method: m[1], url: m[2] } : null;
}

function parseAssertStatusStep(line) {
  const m = line.match(/^ASSERT_STATUS\s+(\d+)/);
  return m ? { type: 'ASSERT', raw: line, assertType: 'STATUS', statusCode: m[1] } : null;
}

function parseAssertJsonStep(line) {
  const m = line.match(/^ASSERT_JSON\s+"([^"]+)"\s+"([^"]+)"/);
  return m ? { type: 'ASSERT', raw: line, assertType: 'JSON', jsonPath: m[1], jsonExpected: m[2] } : null;
}

function parseAssertJsonOpStep(line) {
  const m = line.match(/^ASSERT_JSON\s+(\S+)\s*([<>=!]+)\s*(\S+)/);
  return m ? { type: 'ASSERT', raw: line, assertType: 'JSON', jsonPath: m[1], jsonOp: m[2], jsonExpected: m[3] } : null;
}

function parseAssertSensorStep(line) {
  const m = line.match(/^ASSERT_SENSOR\s+"([^"]+)"\s+"([<>=!]+)"\s+"([^"]+)"\s+"([^"]+)"/);
  return m ? {
    type: 'ASSERT', raw: line, assertType: 'SENSOR',
    parameter: m[1], condition: m[2], value: m[3], unit: m[4],
  } : null;
}

function parseAssertGenericStep(line) {
  return line.startsWith('ASSERT_') ? { type: 'ASSERT', raw: line } : null;
}

function parseNavigateStep(line) {
  const m = _matchFirst(line, [/^NAVIGATE\s+"([^"]+)"/, /^NAVIGATE\s+'([^']+)'/]);
  return m ? { type: 'NAVIGATE', raw: line, url: m[1] } : null;
}

const KEYWORD_STEP_TYPES = ['CLICK', 'INPUT', 'SELECT_DEVICE', 'SELECT_INTERVAL', 'RECORD_START'];

function parseKeywordStep(line) {
  const type = KEYWORD_STEP_TYPES.find((kw) => line.startsWith(kw));
  return type ? { type, raw: line } : null;
}

const STEP_PARSERS = [
  parseSetNameStep, parseSetValStep, parseSetMinStep, parseSetMaxStep,
  parseWaitStep, parseSetQuotedStep, parseSetDblQuotedStep, parseSampleStep,
  parseFuncCallStep, parseTaskDialogStep, parseMotorMoveStep, parseIfNumericRangeStep, parseLegacyCheckStep,
  parseLegacyMinStep, parseLegacyMaxStep, parsePassFailStep, parseLegacyValStep, parseLegacyIfElseStep,
  parseIfDeltaStep, parseIfComparisonStep, parseSaveStep, parseLogStep,
  parseCorrectStep, parseErrorStep, parseExpectStep, parseApiStep,
  parseAssertStatusStep, parseAssertJsonStep, parseAssertJsonOpStep, parseAssertSensorStep,
  parseAssertGenericStep, parseNavigateStep, parseKeywordStep,
];

function parseStep(line) {
  for (const parser of STEP_PARSERS) {
    const step = parser(line);
    if (step) return step;
  }
  return { type: 'OTHER', raw: line };
}

function splitValueUnit(s) {
  const m = s.match(/^([\-\d.]+)\s*(.*)$/);
  if (m) return { value: m[1], unit: m[2] || undefined };
  return { value: s, unit: undefined };
}

function quotedTokens(s) {
  const tokens = [];
  const re = /['"]([^'"]+)['"]/g;
  let match;
  while ((match = re.exec(s || '')) !== null) tokens.push(match[1]);
  return tokens;
}

function lastRangeValue(part) {
  const quoted = quotedTokens(part);
  if (quoted.length) return quoted[quoted.length - 1];

  const trimmed = String(part || '').trim();
  const match = trimmed.match(/[-+]?\d+(?:\.\d+)?(?:\s*[^\s'"]+)?|[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż_][^\s'"]*/g);
  return match?.length ? match[match.length - 1].trim() : trimmed;
}

function parseIfRangeStep(line) {
  const match = line.match(/^IF\s+['"]([^'"]+)['"]\s+(.+)/i);
  if (!match) return null;

  const parameter = match[1];
  const body = match[2].replace(/\s+ELSE\s+.*$/i, '').trim();

  const singleRange = quotedTokens(body).find((token) => token.includes('..'));
  if (singleRange) {
    const [minRaw, maxRaw] = singleRange.split('..').map((item) => item.trim());
    const min = splitValueUnit(minRaw);
    const max = splitValueUnit(maxRaw);
    return {
      type: 'CHECK',
      raw: line,
      parameter,
      min: min.value,
      max: max.value,
      unit: max.unit || min.unit,
      _legacy: 'IF_RANGE',
    };
  }

  if (!body.includes('..')) return null;

  const [left, right] = body.split('..', 2);
  const leftTokens = quotedTokens(left);
  const channel = leftTokens.length > 1 ? leftTokens[0] : '';
  const minRaw = lastRangeValue(left);
  const maxRaw = lastRangeValue(right);
  const min = splitValueUnit(minRaw);
  const max = splitValueUnit(maxRaw);

  return {
    type: 'CHECK',
    raw: line,
    parameter: channel ? `${parameter} ${channel}` : parameter,
    min: min.value,
    max: max.value,
    unit: max.unit || min.unit,
    _legacy: 'IF_RANGE',
  };
}

function _ensureThreshold(map, key) {
  if (!map[key]) map[key] = { parameter: key };
  return map[key];
}

function _applyGoalThreshold(map, goal) {
  if (!goal.val) return;
  const entry = _ensureThreshold(map, goal.val);
  if (goal.min) entry.min = goal.min;
  if (goal.max) entry.max = goal.max;
  entry.unit = goal.minUnit || goal.maxUnit || goal.valUnit || entry.unit;
}

function _applyScalarCondition(entry, step) {
  if (!step.condition || step.value == null) return;
  if (step.condition === '>=' || step.condition === '>') {
    entry.min = entry.min || step.value;
    return;
  }
  if (step.condition === '<=' || step.condition === '<') {
    entry.max = entry.max || step.value;
    return;
  }
  if (step.condition === '=' && entry.min == null && entry.max == null) {
    entry.min = step.value;
    entry.max = step.value;
  }
}

function _applyStepThreshold(map, step) {
  if (step.type !== 'CHECK' || !step.parameter) return;
  const entry = _ensureThreshold(map, step.parameter);
  if (step.min) entry.min = entry.min || step.min;
  if (step.max) entry.max = entry.max || step.max;
  _applyScalarCondition(entry, step);
  if (step.unit) entry.unit = entry.unit || step.unit;
}

function _applyVerdictThreshold(map, step) {
  if ((step.type !== 'PASS' && step.type !== 'FAIL') || !step.parameter) return;
  const entry = _ensureThreshold(map, step.parameter);
  if (step.type === 'PASS') entry.pass_message = step.message;
  if (step.type === 'FAIL') entry.fail_message = step.message;
}

/**
 * Collect threshold data from a goal's metadata and CHECK steps.
 */
export function collectThresholds(goal) {
  const map = {};
  _applyGoalThreshold(map, goal);
  for (const step of goal.steps) {
    _applyStepThreshold(map, step);
    _applyVerdictThreshold(map, step);
  }
  return Object.values(map);
}

function _buildReportStep(s) {
  const step = {
    name: s.type === 'CHECK' ? s.raw : (s.parameter || s.raw),
    status: 'pending',
    duration_ms: 0,
  };
  if (s.parameter) step.parameter = s.parameter;
  if (s.value != null) step.value = s.value;
  if (s.unit) step.unit = s.unit;
  if (s.min) step.min = s.min;
  if (s.max) step.max = s.max;
  if (s.correctMsg) step.pass_message = s.correctMsg;
  if (s.errorMsg) step.fail_message = s.errorMsg;
  return step;
}

function _buildReportGoal(g) {
  const thresholds = collectThresholds(g);
  const steps = g.steps
    .filter(s => s.type !== 'COMMENT')
    .map(_buildReportStep);

  const goalObj = { name: g.name, steps, thresholds };
  if (g.val) goalObj.val = g.val;
  if (g.min) goalObj.min = g.min;
  if (g.max) goalObj.max = g.max;
  if (g.minUnit) goalObj.min_unit = g.minUnit;
  if (g.maxUnit) goalObj.max_unit = g.maxUnit;
  return goalObj;
}

function _buildReportScenario(parsed, goals) {
  return {
    source: parsed.scenarioName || 'editor',
    ok: true,
    duration_ms: 0,
    passed: 0,
    failed: 0,
    total: goals.reduce((sum, g) => sum + g.steps.length, 0),
  };
}

function _buildReportMetadata(parsed) {
  return {
    device_type: parsed.deviceType || '',
    device_model: parsed.deviceModel || '',
    manufacturer: parsed.manufacturer || '',
  };
}

/**
 * Convert parsed OQL structure to oqlos-report-v1 data.json format.
 */
export function toReportJson(parsed) {
  const goals = parsed.goals.map(_buildReportGoal);
  return {
    $schema: 'oqlos-report-v1',
    generated_at: new Date().toISOString(),
    scenario: _buildReportScenario(parsed, goals),
    metadata: _buildReportMetadata(parsed),
    goals,
    variables: {},
    errors: [],
    warnings: [],
  };
}
