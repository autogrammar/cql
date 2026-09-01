/**
 * Map @semcod/oqlts parseOql AST → UI step model (connect-scenario renderer).
 * Single source of truth: grammar lives in packages/oqlts only.
 */

export function applyGoalMeta(goal, step) {
  if (step._goalMeta === 'NAME') {
    goal.name = step.value;
    return;
  }
  if (step._goalMeta === 'VAL') {
    goal.val = step.parameter;
    if (step.unit) goal.valUnit = step.unit;
    return;
  }
  if (step._goalMeta === 'MIN') {
    goal.min = step.value;
    if (step.unit) goal.minUnit = step.unit;
    return;
  }
  if (step._goalMeta === 'MAX') {
    goal.max = step.value;
    if (step.unit) goal.maxUnit = step.unit;
  }
}

export function attachVerdictToChecks(goal) {
  const byParam = {};
  for (const step of goal.steps) {
    if (step.type === 'PASS' && step.parameter) {
      byParam[step.parameter] = byParam[step.parameter] || {};
      byParam[step.parameter].correctMsg = step.message;
    }
    if (step.type === 'FAIL' && step.parameter) {
      byParam[step.parameter] = byParam[step.parameter] || {};
      byParam[step.parameter].errorMsg = step.message;
    }
  }
  for (const step of goal.steps) {
    if (step.type !== 'CHECK' || !step.parameter || !byParam[step.parameter]) continue;
    step.correctMsg = step.correctMsg || byParam[step.parameter].correctMsg;
    step.errorMsg = step.errorMsg || byParam[step.parameter].errorMsg;
  }
}

export function foldTaskDialogSteps(steps) {
  const out = [];
  let dialog = null;

  const flushDialog = () => {
    if (!dialog) return;
    out.push({
      type: 'DIALOG',
      raw: dialog.raw,
      title: dialog.title,
      expectedVal: dialog.expectedVal,
      passMsg: dialog.passMsg,
      failMsg: dialog.failMsg,
    });
    dialog = null;
  };

  for (const step of steps) {
    if (step.type === 'TASK_DIALOG_LINE') {
      if (!dialog) dialog = { raw: step.raw, title: '', expectedVal: '', passMsg: '', failMsg: '' };
      dialog.raw = dialog.raw ? `${dialog.raw}\n${step.raw}` : step.raw;
      if (step.field === 'title') dialog.title = step.value;
      if (step.field === 'val') dialog.expectedVal = step.value;
      if (step.field === 'pass') dialog.passMsg = step.value;
      if (step.field === 'fail') dialog.failMsg = step.value;
      continue;
    }
    flushDialog();
    out.push(step);
  }
  flushDialog();
  return out;
}

export function finalizeGoal(goal) {
  goal.steps = foldTaskDialogSteps(goal.steps);
  attachVerdictToChecks(goal);
}

function attachMessageToPrevious(steps, step) {
  const prev = steps[steps.length - 1];
  if (!prev || (prev.type !== 'CHECK' && prev.type !== 'IF')) return false;
  if (step.type === 'CORRECT' || step.type === 'PASS') {
    prev.correctMsg = step.message;
  } else {
    prev.errorMsg = step.message;
  }
  return true;
}

import { CMD_UI_MAPPERS } from './oqlCmdMappers.js';

/** @param {import('@semcod/oqlts').OqlCommand} cmd */
export function cmdToUiStep(cmd) {
  const name = String(cmd.cmd || '').toUpperCase();
  const mapper = CMD_UI_MAPPERS[name];
  if (mapper) return mapper(cmd);
  return { type: 'OTHER', raw: cmd.raw, cmd: name };
}

function applyGoalCommand(goal, cmd) {
  const step = cmdToUiStep(cmd);
  if (!step) return;

  if (step.type === 'SET' && step._goalMeta) {
    applyGoalMeta(goal, step);
    return;
  }

  if ((step.type === 'CORRECT' || step.type === 'ERROR') && attachMessageToPrevious(goal.steps, step)) {
    return;
  }
  if ((step.type === 'PASS' || step.type === 'FAIL') && !step.parameter && attachMessageToPrevious(goal.steps, step)) {
    return;
  }

  goal.steps.push(step);
}

/** @param {import('@semcod/oqlts').OqlParseResult} parseResult */
export function astToSteps(parseResult) {
  const { scenario } = parseResult;
  const result = {
    scenarioName: scenario.title || scenario.meta.scenario || '',
    deviceType: scenario.meta.device_type || '',
    deviceModel: scenario.meta.device_model || '',
    manufacturer: scenario.meta.manufacturer || '',
    goals: [],
    funcs: [],
  };

  for (const goal of scenario.goals) {
    const uiGoal = { name: goal.name, steps: [] };
    for (const cmd of goal.steps) {
      applyGoalCommand(uiGoal, cmd);
    }
    finalizeGoal(uiGoal);
    result.goals.push(uiGoal);
  }

  for (const block of scenario.blocks) {
    if (block.type !== 'FUNC') continue;
    const func = { name: block.name, steps: [] };
    for (const cmd of block.cmds) {
      const step = cmdToUiStep(cmd);
      if (step) func.steps.push(step);
    }
    result.funcs.push(func);
  }

  return result;
}
