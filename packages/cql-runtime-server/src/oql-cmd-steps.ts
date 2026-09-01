/**
 * OQL command → legacy UI step mapping (extracted from oql-runtime-ssot.ts).
 */
import type { OqlCommand } from '@semcod/oqlts';

export type LegacyStep = Record<string, unknown>;

function str(value: unknown): string {
  return value == null ? '' : String(value);
}

function stepsForSet(args: Record<string, unknown>): LegacyStep[] {
  const target = str(args.target);
  if (target.toUpperCase() === 'NAME') return [];
  return [{ type: 'set', parameter: target, value: str(args.value), unit: args.unit }];
}

function stepsForWait(args: Record<string, unknown>): LegacyStep[] {
  return [{ type: 'wait', duration: str(args.value ?? args.raw), unit: args.unit }];
}

function stepsForMinMax(type: 'min' | 'max', args: Record<string, unknown>): LegacyStep[] {
  return [{ type, parameter: str(args.sensor), value: str(args.value), unit: args.unit }];
}

function stepsForRange(args: Record<string, unknown>): LegacyStep[] {
  const unit = args.unit;
  return [
    { type: 'min', parameter: str(args.sensor), value: str(args.min), unit },
    { type: 'max', parameter: str(args.sensor), value: str(args.max), unit },
  ];
}

function stepsForPass(args: Record<string, unknown>): LegacyStep[] {
  if (args.sensor) {
    return [{ type: 'pass', parameter: str(args.sensor), message: str(args.message) }];
  }
  return [{ type: 'info', level: 'CORRECT', message: str(args.message) }];
}

function stepsForFail(args: Record<string, unknown>): LegacyStep[] {
  const step: LegacyStep = { message: str(args.message) };
  if (args.sensor) {
    step.type = 'fail';
    step.parameter = str(args.sensor);
  } else {
    step.type = 'error';
  }
  if (args.goto) step.goto = str(args.goto);
  if (args.retry != null) step.retry = args.retry;
  return [step];
}

function stepsForTask(args: Record<string, unknown>): LegacyStep[] {
  return [{ type: 'task_dialog_line', field: str(args.field), value: str(args.value) }];
}

function stepsForSample(args: Record<string, unknown>): LegacyStep[] {
  return [{
    type: 'sample',
    parameter: str(args.sensor),
    state: str(args.direction).toUpperCase(),
    interval: str(args.interval_ms) || null,
  }];
}

function stepsForIf(args: Record<string, unknown>): LegacyStep[] {
  return [{
    type: 'if',
    parameter: str(args.param),
    operator: str(args.operator),
    value: str(args.value),
    unit: args.unit,
  }];
}

type CmdHandler = (args: Record<string, unknown>) => LegacyStep[];

const CMD_HANDLERS: Record<string, CmdHandler> = {
  SET: stepsForSet,
  WAIT: stepsForWait,
  MIN: (args) => stepsForMinMax('min', args),
  MAX: (args) => stepsForMinMax('max', args),
  RANGE: stepsForRange,
  PASS: stepsForPass,
  FAIL: stepsForFail,
  TASK: stepsForTask,
  LOG: (args) => [{ type: 'log', message: str(args.message) }],
  GET: (args) => [{ type: 'get', parameter: str(args.sensor), unit: args.unit }],
  READ: (args) => [{ type: 'get', parameter: str(args.sensor), unit: args.unit }],
  VAL: (args) => [{ type: 'val', parameter: str(args.param), unit: args.unit }],
  SAVE: (args) => [{ type: 'save', parameter: str(args.label) }],
  SAMPLE: stepsForSample,
  IF: stepsForIf,
};

export function cmdToSteps(cmd: OqlCommand): LegacyStep[] {
  const name = str(cmd.cmd).toUpperCase();
  const args = (cmd.args ?? {}) as Record<string, unknown>;
  const handler = CMD_HANDLERS[name];
  if (handler) return handler(args);
  return [{ type: 'other', cmd: name, args, raw: cmd.raw }];
}
