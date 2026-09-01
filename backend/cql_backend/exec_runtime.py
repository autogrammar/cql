"""Python port of `oqlos/cql/runtime/dsl.exec.ts` + `dsl.engine.ts` + `dsl-execution.handlers.ts`.

DSL execution engine that produces an execution plan.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable

from .parser import parse_dsl
from .types import (
    DslAst,
    DslGoal,
    DslIfCondition,
    DslStep,
    ExecContext,
    ExecPlanStep,
    ExecResult,
    ParseResult,
)

# Unit conversion info
DEFAULT_UNIT_INFO = {'family': None, 'toBase': 1.0}

UNIT_INFO_BY_CODE: dict[str, dict[str, Any]] = {
    'ms': {'family': 'time', 'toBase': 1e-3},
    's': {'family': 'time', 'toBase': 1.0},
    'sec': {'family': 'time', 'toBase': 1.0},
    'min': {'family': 'time', 'toBase': 60.0},
    'h': {'family': 'time', 'toBase': 3600.0},
    'pa': {'family': 'pressure', 'toBase': 1.0},
    'kpa': {'family': 'pressure', 'toBase': 1e3},
    'mpa': {'family': 'pressure', 'toBase': 1e6},
    'mbar': {'family': 'pressure', 'toBase': 100.0},
    'bar': {'family': 'pressure', 'toBase': 1e5},
}


def _to_number(v: Any) -> float | None:
    if isinstance(v, (int, float)) and math.isfinite(v):
        return float(v)
    if isinstance(v, str):
        m = re.match(r'^(-?\d+(?:[.,]\d+)?)', v.strip())
        if m:
            n = float(m.group(1).replace(',', '.'))
            if math.isfinite(n):
                return n
    return None


def _cmp(op: str, left: Any, right: Any) -> bool | None:
    ln = _to_number(left)
    rn = _to_number(right)
    if ln is not None and rn is not None:
        if op == '>':
            return ln > rn
        if op == '<':
            return ln < rn
        if op == '=':
            return ln == rn
        if op == '>=':
            return ln >= rn
        if op == '<=':
            return ln <= rn
    if op == '=':
        return str(left) == str(right)
    return None


def _normalize_state_key(name: str) -> str:
    return str(name or '').strip()


def _norm_unit(u: str | None) -> str | None:
    return u.strip().lower() if u else None


def _get_unit_info(u: str | None) -> dict[str, Any]:
    normalized = _norm_unit(u)
    return UNIT_INFO_BY_CODE.get(normalized, DEFAULT_UNIT_INFO)


def _to_base(num: float, unit: str | None = None) -> dict[str, Any]:
    info = _get_unit_info(unit)
    return {'base': num * info['toBase'], 'family': info['family']}


def _get_numeric_value(value: Any) -> float | None:
    num = _to_number(value)
    return num if num is not None else (float(value) if isinstance(value, (int, float)) else None)


# Execution helpers class
class ExecutionHelpers:
    def __init__(
        self,
        state: dict[str, Any],
        state_units: dict[str, str | None],
        sample_buffers: dict[str, list[float]],
        ctx: ExecContext | None
    ):
        self.state = state
        self.state_units = state_units
        self.sample_buffers = sample_buffers
        self.ctx = ctx

    def get_var(self, name: str) -> Any:
        key = _normalize_state_key(name)
        if not key:
            return None
        if key in self.state:
            return self.state[key]
        try:
            if self.ctx and hasattr(self.ctx, 'getParamValue') and callable(self.ctx.getParamValue):
                return self.ctx.getParamValue(key)
        except Exception:
            pass
        return None

    def set_var(self, name: str, raw_value: Any, unit: str | None = None) -> None:
        key = _normalize_state_key(name)
        if not key:
            return
        composed = f'{raw_value} {unit}' if unit else raw_value
        num = _to_number(composed)
        self.state[key] = num if num is not None else composed
        if unit:
            self.state_units[key] = _norm_unit(unit)

    def get_var_unit(self, name: str) -> str | None:
        return self.state_units.get(_normalize_state_key(name))

    def evaluate_fun_expression(self, expr: str) -> float | None:
        expression_with_values = self._replace_expression_variables(expr)
        if expression_with_values is None:
            return None
        return self._evaluate_numeric_expression(self._normalize_function_expression(expression_with_values))

    def _replace_expression_variables(self, expr: str) -> str | None:
        eval_expr = expr
        for match in re.finditer(r'\[([^\]]+)\]', expr):
            var_name = match.group(1).strip()
            value = self.get_var(var_name)
            num = _to_number(value)
            if num is None:
                return None
            escaped = re.escape(match.group(0))
            eval_expr = re.sub(escaped, str(num), eval_expr)
        return eval_expr

    def _normalize_function_expression(self, expr: str) -> str:
        return (
            expr.replace('ABS(', 'math.abs(').replace('SQRT(', 'math.sqrt(')
            .replace('LOG(', 'math.log(').replace('EXP(', 'math.exp(')
            .replace('ROUND(', 'math.round(').replace('POW(', 'math.pow(')
            .replace('^', '**')
        )

    def _evaluate_numeric_expression(self, expr: str) -> float | None:
        try:
            # Safe evaluation - only allow math operations
            allowed_names = {'math': math, 'abs': abs, 'max': max, 'min': min}
            result = eval(expr, {'__builtins__': {}}, allowed_names)  # noqa: S307
            return float(result) if isinstance(result, (int, float)) and math.isfinite(result) else None
        except Exception:
            return None

    def calc_aggregate(self, fn: str, input_name: str) -> float | None:
        buffer = self._get_aggregate_buffer(input_name)
        return self._calculate_aggregate_value(fn, buffer)

    def _get_aggregate_buffer(self, input_name: str) -> list[float]:
        buffer = self.sample_buffers.get(input_name, [])
        if not buffer:
            value = self.get_var(input_name)
            num = _to_number(value)
            if num is not None:
                buffer = [num]
                self.sample_buffers[input_name] = buffer
        return buffer

    def _calculate_aggregate_value(self, fn: str, buffer: list[float]) -> float | None:
        if not buffer:
            return None
        fn_upper = fn.upper()
        if fn_upper == 'AVG':
            return sum(buffer) / len(buffer)
        if fn_upper == 'SUM':
            return sum(buffer)
        if fn_upper == 'MIN':
            return min(buffer)
        if fn_upper == 'MAX':
            return max(buffer)
        if fn_upper == 'COUNT':
            return float(len(buffer))
        if fn_upper == 'STDDEV':
            avg = sum(buffer) / len(buffer)
            sq_diffs = [(v - avg) ** 2 for v in buffer]
            return math.sqrt(sum(sq_diffs) / len(buffer))
        return None

    def resolve_param(self, name: str) -> dict[str, Any]:
        value = self.get_var(name)
        return {'num': _get_numeric_value(value), 'unit': self.get_var_unit(name)}

    def resolve_literal(self, value: Any, unit_arg: str | None = None) -> dict[str, Any]:
        if isinstance(value, str) and value and not unit_arg:
            named_literal = self._resolve_named_literal(value)
            if named_literal:
                return named_literal
        literal_with_unit = self._resolve_literal_with_unit(value, unit_arg)
        if literal_with_unit:
            return literal_with_unit
        numeric_string_literal = self._resolve_numeric_string_literal(value)
        if numeric_string_literal:
            return numeric_string_literal
        return {'num': _get_numeric_value(value), 'unit': None}

    def _resolve_named_literal(self, value: str) -> dict[str, Any] | None:
        key = _normalize_state_key(value)
        resolved = self.get_var(key)
        if resolved is None:
            return None
        return {'num': _get_numeric_value(resolved), 'unit': self.get_var_unit(key)}

    def _resolve_literal_with_unit(self, value: Any, unit_arg: str | None) -> dict[str, Any] | None:
        if not unit_arg:
            return None
        num = _to_number(f'{value} {unit_arg}')
        return {'num': num if num is not None else None, 'unit': _norm_unit(unit_arg)}

    def _resolve_numeric_string_literal(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        match = re.match(r'^(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)?$', trimmed)
        if not match:
            return None
        num = float(match.group(1).replace(',', '.'))
        return None if math.isnan(num) else {'num': num, 'unit': _norm_unit(match.group(2))}

    def compare_with_units(self, op: str, left: dict[str, Any], right: dict[str, Any]) -> bool | None:
        if left.get('num') is None or right.get('num') is None:
            return None
        left_unit = _norm_unit(left.get('unit'))
        right_unit = _norm_unit(right.get('unit'))
        if not left_unit and not right_unit:
            return _cmp(op, left['num'], right['num'])
        if left_unit and right_unit and left_unit == right_unit:
            return _cmp(op, left['num'], right['num'])
        left_base = _to_base(left['num'], left_unit)
        right_base = _to_base(right['num'], right_unit)
        same_family_result = self._compare_with_same_family(op, left_base, right_base)
        if same_family_result is not None:
            return same_family_result
        return self._compare_with_mixed_family(op, left['num'], left_base, right['num'], right_base)

    def _compare_with_same_family(
        self, op: str, left_base: dict[str, Any], right_base: dict[str, Any]
    ) -> bool | None:
        if left_base['family'] and right_base['family'] and left_base['family'] == right_base['family']:
            return _cmp(op, left_base['base'], right_base['base'])
        return None

    def _compare_with_mixed_family(
        self, op: str, left_num: float, left_base: dict[str, Any],
        right_num: float, right_base: dict[str, Any]
    ) -> bool | None:
        family = left_base['family'] or right_base['family']
        if family:
            left_value = left_base['base'] if left_base['family'] else left_num
            right_value = right_base['base'] if right_base['family'] else right_num
            return _cmp(op, left_value, right_value)
        return _cmp(op, left_num, right_num)


# Helper to get attributes from dict or Pydantic model
def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


# Step handlers
def _handle_if_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    lhs = h.resolve_param(_get_attr(s, 'parameter', ''))
    rhs = h.resolve_literal(_get_attr(s, 'value'), _get_attr(s, 'unit'))
    passed = h.compare_with_units(_get_attr(s, 'operator', '='), lhs, rhs)
    plan = state.get('plan', [])
    plan.append({'kind': 'condition', 'condition': s, 'passed': passed})


def _handle_else_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'else', 'else': s})


def _handle_task_step(s: Any, ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    t = {'function': _get_attr(s, 'function'), 'object': _get_attr(s, 'object'), 'ands': _get_attr(s, 'ands')}
    plan = state.get('plan', [])
    plan.append({'kind': 'task', 'task': t})
    try:
        if ctx and hasattr(ctx, 'executeTasks') and ctx.executeTasks and hasattr(ctx, 'runTask') and callable(ctx.runTask):
            ctx.runTask(t['function'], t['object'])
    except Exception:
        pass


def _handle_pump_step(s: Any, ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    raw = _get_attr(s, 'raw') or ' '.join(filter(None, [str(_get_attr(s, 'value', '')), str(_get_attr(s, 'unit', ''))])).strip()
    plan = state.get('plan', [])
    plan.append({'kind': 'pump', 'value': _get_attr(s, 'value'), 'unit': _get_attr(s, 'unit'), 'raw': raw})
    try:
        if ctx and hasattr(ctx, 'executeTasks') and ctx.executeTasks and hasattr(ctx, 'runTask') and callable(ctx.runTask):
            ctx.runTask('PUMP', raw)
    except Exception:
        pass


def _handle_func_call_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'func_call', 'name': _get_attr(s, 'name'), 'arguments': _get_attr(s, 'arguments')})


def _handle_get_step(s: Any, ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'parameter', '')).strip()
    cur = h.get_var(key)
    if cur is None:
        try:
            if ctx and hasattr(ctx, 'getParamValue') and callable(ctx.getParamValue):
                v = ctx.getParamValue(key)
                if v is not None:
                    state['state'][key] = v
        except Exception:
            pass
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'GET', 'parameter': _get_attr(s, 'parameter'), 'value': h.get_var(key), 'unit': _get_attr(s, 'unit')})


def _handle_set_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    h.set_var(_get_attr(s, 'parameter'), _get_attr(s, 'value'), _get_attr(s, 'unit'))
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'SET', 'parameter': _get_attr(s, 'parameter'), 'value': _get_attr(s, 'value'), 'unit': _get_attr(s, 'unit')})
    param_str = str(_get_attr(s, 'parameter', '')).strip().lower()
    if param_str in ('wait', 'delay', 'timeout', 'pause'):
        plan.append({'kind': 'wait', 'duration': _get_attr(s, 'value'), 'unit': _get_attr(s, 'unit')})


def _resolve_unit_aware_value(
    lhs: float | None, lhs_unit: str | None,
    rhs: float | None, rhs_unit: str | None,
    fn: Callable[[float, float], float], h: ExecutionHelpers
) -> float | None:
    if lhs is not None and rhs is not None:
        lb = _to_base(lhs, lhs_unit)
        rb = _to_base(rhs, rhs_unit)
        if lb['family'] and rb['family'] and lb['family'] == rb['family']:
            result = fn(lb['base'], rb['base']) / _get_unit_info(lhs_unit)['toBase']
            return result
        return fn(lhs, rhs)
    return rhs if rhs is not None else None


def _handle_max_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'parameter', '')).strip()
    lit = h.resolve_literal(_get_attr(s, 'value'), _get_attr(s, 'unit'))
    cur = h.resolve_param(key)
    result = _resolve_unit_aware_value(cur.get('num'), cur.get('unit'), lit.get('num'), lit.get('unit'), max, h)
    if result is not None:
        state['state'][key] = result
    if _get_attr(s, 'unit'):
        state['state_units'][key] = _norm_unit(_get_attr(s, 'unit'))
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'MAX', 'parameter': _get_attr(s, 'parameter'), 'value': state['state'].get(key, _get_attr(s, 'value')), 'unit': _get_attr(s, 'unit')})


def _handle_min_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'parameter', '')).strip()
    lit = h.resolve_literal(_get_attr(s, 'value'), _get_attr(s, 'unit'))
    cur = h.resolve_param(key)
    result = _resolve_unit_aware_value(cur.get('num'), cur.get('unit'), lit.get('num'), lit.get('unit'), min, h)
    if result is not None:
        state['state'][key] = result
    if _get_attr(s, 'unit'):
        state['state_units'][key] = _norm_unit(_get_attr(s, 'unit'))
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'MIN', 'parameter': _get_attr(s, 'parameter'), 'value': state['state'].get(key, _get_attr(s, 'value')), 'unit': _get_attr(s, 'unit')})


def _handle_delta_max_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'DELTA_MAX', 'parameter': _get_attr(s, 'parameter'), 'value': _get_attr(s, 'value'), 'unit': _get_attr(s, 'unit'), 'per': _get_attr(s, 'per')})


def _handle_delta_min_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'DELTA_MIN', 'parameter': _get_attr(s, 'parameter'), 'value': _get_attr(s, 'value'), 'unit': _get_attr(s, 'unit'), 'per': _get_attr(s, 'per')})


def _handle_val_step(s: Any, ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'parameter', '')).strip()
    try:
        if ctx and hasattr(ctx, 'getParamValue') and callable(ctx.getParamValue):
            v = ctx.getParamValue(key)
            if v is not None:
                state['state'][key] = _to_number(v) or v
                if _get_attr(s, 'unit'):
                    state['state_units'][key] = _norm_unit(_get_attr(s, 'unit'))
    except Exception:
        pass
    plan = state.get('plan', [])
    plan.append({'kind': 'var', 'action': 'VAL', 'parameter': _get_attr(s, 'parameter'), 'value': state['state'].get(key), 'unit': _get_attr(s, 'unit')})


def _handle_wait_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'wait', 'duration': _get_attr(s, 'duration'), 'unit': _get_attr(s, 'unit')})


def _handle_log_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'message', 'level': 'LOG', 'message': _get_attr(s, 'message')})


def _handle_alarm_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'message', 'level': 'ALARM', 'message': _get_attr(s, 'message')})


def _handle_error_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'message', 'level': 'ERROR', 'message': _get_attr(s, 'message')})


def _handle_save_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'save', 'parameter': _get_attr(s, 'parameter')})


def _handle_user_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'user', 'action': _get_attr(s, 'action'), 'message': _get_attr(s, 'message')})


def _handle_result_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'result', 'status': _get_attr(s, 'status')})


def _handle_opt_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'opt', 'parameter': _get_attr(s, 'parameter'), 'description': _get_attr(s, 'description')})


def _handle_repeat_step(_s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'repeat'})


def _handle_end_step(_s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'end'})


def _handle_out_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'out', 'outType': _get_attr(s, 'outType'), 'value': _get_attr(s, 'value')})


def _handle_dialog_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'dialog', 'parameter': _get_attr(s, 'parameter'), 'message': _get_attr(s, 'message')})


def _handle_info_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    plan = state.get('plan', [])
    plan.append({'kind': 'info', 'level': _get_attr(s, 'level'), 'message': _get_attr(s, 'message')})


def _handle_sample_step(s: Any, _ctx: Any, state: dict[str, Any], _h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'parameter', '')).strip()
    if _get_attr(s, 'state') == 'START':
        state['sample_buffers'][key] = []
    plan = state.get('plan', [])
    plan.append({'kind': 'sample', 'parameter': _get_attr(s, 'parameter'), 'state': _get_attr(s, 'state'), 'interval': _get_attr(s, 'interval')})


def _handle_calc_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'result', '')).strip()
    val = h.calc_aggregate(_get_attr(s, 'function'), _get_attr(s, 'input'))
    if val is not None:
        state['state'][key] = val
    plan = state.get('plan', [])
    plan.append({'kind': 'calc', 'result': _get_attr(s, 'result'), 'function': _get_attr(s, 'function'), 'input': _get_attr(s, 'input'), 'value': val})


def _handle_fun_step(s: Any, _ctx: Any, state: dict[str, Any], h: ExecutionHelpers) -> None:
    key = str(_get_attr(s, 'result', '')).strip()
    val = h.evaluate_fun_expression(_get_attr(s, 'expression'))
    if val is not None:
        state['state'][key] = val
    plan = state.get('plan', [])
    plan.append({'kind': 'fun', 'result': _get_attr(s, 'result'), 'expression': _get_attr(s, 'expression'), 'value': val})


# Step handler registry
STEP_HANDLERS: dict[str, Callable[..., None]] = {
    'if': _handle_if_step,
    'else': _handle_else_step,
    'task': _handle_task_step,
    'pump': _handle_pump_step,
    'func_call': _handle_func_call_step,
    'get': _handle_get_step,
    'set': _handle_set_step,
    'max': _handle_max_step,
    'min': _handle_min_step,
    'delta_max': _handle_delta_max_step,
    'delta_min': _handle_delta_min_step,
    'val': _handle_val_step,
    'wait': _handle_wait_step,
    'log': _handle_log_step,
    'alarm': _handle_alarm_step,
    'error': _handle_error_step,
    'save': _handle_save_step,
    'user': _handle_user_step,
    'result': _handle_result_step,
    'opt': _handle_opt_step,
    'repeat': _handle_repeat_step,
    'end': _handle_end_step,
    'out': _handle_out_step,
    'dialog': _handle_dialog_step,
    'info': _handle_info_step,
    'sample': _handle_sample_step,
    'calc': _handle_calc_step,
    'fun': _handle_fun_step,
}


def _coerce_ast(ast: DslAst | dict[str, Any]) -> DslAst:
    if not isinstance(ast, dict):
        return ast
    from pydantic import TypeAdapter
    from .types import DslAst as DslAstType
    return TypeAdapter(DslAstType).validate_python(ast)


def _run_goal_steps(
    goal: Any,
    ctx: ExecContext | None,
    exec_state: dict[str, Any],
    helpers: ExecutionHelpers,
) -> None:
    steps = getattr(goal, 'steps', None)
    if not steps:
        return
    plan = exec_state['plan']
    for step in steps:
        step_type = step.get('type') if isinstance(step, dict) else getattr(step, 'type', None)
        handler = STEP_HANDLERS.get(step_type)
        if handler:
            handler(step, ctx, exec_state, helpers)


def _run_legacy_goal(
    goal: Any,
    ctx: ExecContext | None,
    exec_state: dict[str, Any],
    helpers: ExecutionHelpers,
) -> None:
    plan = exec_state['plan']
    for condition in goal.conditions:
        cond_type = condition.get('type') if isinstance(condition, dict) else getattr(condition, 'type', None)
        handler = STEP_HANDLERS.get(cond_type if cond_type == 'if' else 'else')
        if handler:
            handler(condition, ctx, exec_state, helpers)
    for task in goal.tasks:
        is_pump = str(getattr(task, 'function', '') or '').strip().upper() == 'PUMP'
        if is_pump:
            raw = str(getattr(task, 'object', '') or '').strip()
            plan.append({'kind': 'pump', 'value': raw.split()[0] if raw.split() else raw, 'raw': raw})
        else:
            task_dict = {
                'function': getattr(task, 'function', ''),
                'object': getattr(task, 'object', ''),
                'ands': getattr(task, 'ands', []),
            }
            plan.append({'kind': 'task', 'task': task_dict})
        try:
            if ctx and ctx.executeTasks and ctx.runTask:
                ctx.runTask(getattr(task, 'function', ''), getattr(task, 'object', ''))
        except Exception:
            pass


def execute_ast(ast: DslAst | dict[str, Any], ctx: ExecContext | None = None) -> ExecResult:
    """Execute DSL AST using handler registry."""
    errors: list[str] = []
    plan: list[ExecPlanStep] = []
    state: dict[str, Any] = {}
    state_units: dict[str, str | None] = {}
    sample_buffers: dict[str, list[float]] = {}

    helpers = ExecutionHelpers(state, state_units, sample_buffers, ctx)
    exec_state = {'state': state, 'stateUnits': state_units, 'sampleBuffers': sample_buffers, 'plan': plan}
    ast = _coerce_ast(ast)

    for goal in ast.goals:
        plan.append({'kind': 'goal', 'name': goal.name})
        if getattr(goal, 'steps', None):
            _run_goal_steps(goal, ctx, exec_state, helpers)
        else:
            _run_legacy_goal(goal, ctx, exec_state, helpers)

    return ExecResult(ok=len(errors) == 0, errors=errors, ast=ast, plan=plan)


def execute_dsl(input_text: str | DslAst | dict[str, Any], ctx: ExecContext | None = None) -> ExecResult:
    """Execute DSL from text or AST."""
    if isinstance(input_text, str):
        parsed = parse_dsl(input_text)
        if not parsed.ok:
            return ExecResult(ok=False, errors=parsed.errors.copy(), ast=parsed.ast, plan=[])
        return execute_ast(parsed.ast, ctx)
    return execute_ast(input_text, ctx)
