/**
 * Per-command UI step mappers — extracted from cmdToUiStep to reduce cyclomatic complexity.
 */

function mapSetStep(args, raw) {
  const target = String(args.target ?? '');
  const upper = target.toUpperCase();
  if (upper === 'NAME') return null;
  if (upper === 'VAL') {
    return { type: 'SET', _goalMeta: 'VAL', parameter: String(args.value ?? ''), unit: args.unit, raw };
  }
  if (upper === 'MIN') {
    return { type: 'SET', _goalMeta: 'MIN', value: String(args.value ?? ''), unit: args.unit, raw };
  }
  if (upper === 'MAX') {
    return { type: 'SET', _goalMeta: 'MAX', value: String(args.value ?? ''), unit: args.unit, raw };
  }
  return {
    type: 'SET',
    parameter: target,
    value: String(args.value ?? ''),
    unit: args.unit,
    raw,
  };
}

function mapWaitStep(args, raw) {
  return {
    type: 'WAIT',
    value: String(args.value ?? args.raw ?? ''),
    unit: args.unit || 'ms',
    raw,
  };
}

function mapMinMaxStep(args, raw, field) {
  return {
    type: 'CHECK',
    parameter: String(args.sensor ?? ''),
    [field]: String(args.value ?? ''),
    unit: args.unit || undefined,
    raw,
    _legacy: field.toUpperCase(),
  };
}

function mapIfStep(cmd) {
  const args = cmd.args || {};
  const step = {
    type: 'CHECK',
    raw: cmd.raw,
    parameter: String(args.param ?? ''),
    condition: String(args.operator ?? ''),
    value: String(args.value ?? ''),
    _legacy: 'IF',
  };
  const elseClause = args.else;
  if (elseClause && typeof elseClause === 'object') {
    if (elseClause.action === 'ERROR') step.errorMsg = String(elseClause.message ?? '');
    else step.correctMsg = String(elseClause.message ?? '');
  }
  if (args.correct_msg) step.correctMsg = String(args.correct_msg);
  if (args.error_msg) step.errorMsg = String(args.error_msg);
  return step;
}

function mapCheckStep(cmd) {
  const args = cmd.args || {};
  return {
    type: 'CHECK',
    raw: cmd.raw,
    parameter: String(args.sensor ?? ''),
    min: args.min != null ? String(args.min) : undefined,
    max: args.max != null ? String(args.max) : undefined,
    unit: args.unit || undefined,
    correctMsg: args.correct_msg ? String(args.correct_msg) : undefined,
    errorMsg: args.error_msg ? String(args.error_msg) : undefined,
  };
}

function mapPassStep(args, raw) {
  if (args.sensor) {
    return { type: 'PASS', parameter: String(args.sensor), message: String(args.message ?? ''), raw };
  }
  return { type: 'PASS', message: String(args.message ?? ''), raw };
}

function mapFailStep(args, raw) {
  const step = { type: 'FAIL', message: String(args.message ?? ''), raw };
  if (args.sensor) step.parameter = String(args.sensor);
  if (args.goto) step.goto = String(args.goto);
  if (args.retry != null) step.retry = args.retry;
  return step;
}

function mapReadStep(name, args, raw) {
  if (name === 'VAL') {
    return { type: 'SET', parameter: String(args.param ?? ''), unit: args.unit, raw, _read: 'VAL' };
  }
  return { type: 'SET', parameter: String(args.sensor ?? ''), raw, _read: name };
}

function mapFuncStep(args, raw) {
  return {
    type: 'FUNC_CALL',
    funcName: String(args.name ?? args.fn ?? ''),
    args: Array.isArray(args.args) ? args.args.map(String) : [],
    raw,
  };
}

/** @type {Record<string, (cmd: import('@semcod/oqlts').OqlCommand) => object | null>} */
export const CMD_UI_MAPPERS = {
  SET: (cmd) => mapSetStep(cmd.args || {}, cmd.raw),
  WAIT: (cmd) => mapWaitStep(cmd.args || {}, cmd.raw),
  MIN: (cmd) => mapMinMaxStep(cmd.args || {}, cmd.raw, 'min'),
  MAX: (cmd) => mapMinMaxStep(cmd.args || {}, cmd.raw, 'max'),
  RANGE: mapCheckStep,
  CHECK: mapCheckStep,
  IF: mapIfStep,
  PASS: (cmd) => mapPassStep(cmd.args || {}, cmd.raw),
  FAIL: (cmd) => mapFailStep(cmd.args || {}, cmd.raw),
  CORRECT: (cmd) => ({ type: 'CORRECT', message: String((cmd.args || {}).message ?? ''), raw: cmd.raw }),
  ERROR: (cmd) => ({ type: 'ERROR', message: String((cmd.args || {}).message ?? ''), raw: cmd.raw }),
  TASK: (cmd) => ({
    type: 'TASK_DIALOG_LINE',
    field: String((cmd.args || {}).field ?? 'title'),
    value: String((cmd.args || {}).value ?? ''),
    raw: cmd.raw,
  }),
  LOG: (cmd) => ({ type: 'LOG', message: String((cmd.args || {}).message ?? ''), raw: cmd.raw }),
  GET: (cmd) => mapReadStep('GET', cmd.args || {}, cmd.raw),
  READ: (cmd) => mapReadStep('READ', cmd.args || {}, cmd.raw),
  VAL: (cmd) => mapReadStep('VAL', cmd.args || {}, cmd.raw),
  SAVE: (cmd) => ({ type: 'SAVE', parameter: String((cmd.args || {}).label ?? ''), raw: cmd.raw }),
  SAMPLE: (cmd) => ({
    type: 'SAMPLE',
    parameter: String((cmd.args || {}).sensor ?? ''),
    action: String((cmd.args || {}).direction ?? ''),
    interval: (cmd.args || {}).interval_ms != null ? String((cmd.args || {}).interval_ms) : undefined,
    raw: cmd.raw,
  }),
  FUNC: (cmd) => mapFuncStep(cmd.args || {}, cmd.raw),
};
