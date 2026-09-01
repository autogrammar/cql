"""Python port of `oqlos/cql/runtime/dsl.parser.ts`.

Recursive-descent parser producing a JSON-friendly AST matching the TS one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .quotes import normalize_dsl_text_quotes
from .types import (
    DslAst,
    DslElseCondition,
    DslFunc,
    DslGoal,
    DslIfCondition,
    DslStep,
    DslTask,
    DslTaskAnd,
    ParseResult,
)

# Regex constants (ported from TS)
RX_SCENARIO = re.compile(r'^\s*SCENARIO:\s*(.+)$', re.IGNORECASE)
RX_GOAL = re.compile(r'^\s*GOAL:\s*(.+)$', re.IGNORECASE)
RX_FUNC = re.compile(r'^\s*FUNC:\s*(.+)$', re.IGNORECASE)
RX_TASK = re.compile(r'^\s*TASK\s+(\d+)\s*:\s*$', re.IGNORECASE)
RX_TASK_INLINE = re.compile(r'^\s*TASK\s*(?::\s*)?(.+)$', re.IGNORECASE)
RX_ACT = re.compile(r'^\s*→\s*([^\["]+?)\s*(?:\[(.+?)\]|"([^"]*)")\s*$')
RX_AND = re.compile(r'^\s*AND\s+([^\["]+?)\s*(?:\[(.+?)\]|"([^"]*)")\s*$', re.IGNORECASE)
RX_IF_BR = re.compile(r'^\s*IF\s*"([^"]+)"\s*(>=|<=|>|<|=)\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_IF_PAR = re.compile(r'^\s*IF\s*"([^"]+)"\s*\((>=|<=|>|<|=)\)\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_IF_INFIX = re.compile(r'^\s*IF\s*"([^"]+)"\s*(>=|<=|>|<|=)\s*(?:"([^"]*)"|\[([^\]]+)\])\s*$', re.IGNORECASE)
RX_IF_COMPOUND = re.compile(
    r'^\s*IF\s*"([^"]+)"\s*(>=|<=|>|<|=)\s*"([^"]+)"\s+OR\s+"([^"]+)"\s*(>=|<=|>|<|=)\s*"([^"]+)"\s*$',
    re.IGNORECASE
)
RX_IF_COMPOUND_OR_IF = re.compile(
    r'^\s*IF\s*"([^"]+)"\s*(>=|<=|>|<|=)\s*"([^"]+)"\s+OR\s+IF\s+"([^"]+)"\s*(>=|<=|>|<|=)\s*"([^"]+)"\s*$',
    re.IGNORECASE
)
RX_IF_STR = re.compile(r'^\s*IF\s*"([^"]+)"\s*"([^"]*)"', re.IGNORECASE)
RX_IF_OP_STR = re.compile(r'^\s*IF\s*"([^"]+)"\s*(>=|<=|>|<|=|!=)\s*"([^"]*)"', re.IGNORECASE)
RX_OR_IF = re.compile(r'^\s*OR\s+IF\s*"(.+?)"\s*(>=|<=|>|<|=)?\s*"?([^"]*)"?\s*$', re.IGNORECASE)
RX_ELSE = re.compile(r'^\s*ELSE\s+(ERROR|WARNING|INFO|GOAL)\s*"(.*)"\s*$', re.IGNORECASE)
RX_ELSE_PLAIN = re.compile(r'^\s*ELSE\s*$', re.IGNORECASE)
RX_GET = re.compile(r'^\s*GET\s*"([^"]+)"(?:\s*"([^"]+)")?\s*$', re.IGNORECASE)
RX_VAL = re.compile(r'^\s*VAL\s*"([^"]+)"(?:\s*"([^"]+)")?\s*$', re.IGNORECASE)
RX_SET = re.compile(r'^\s*SET\s*"([^"]+)"\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_SET_QUOTED = re.compile(r'^\s*SET\s*"([^"]+)"\s*"([^"]*)"', re.IGNORECASE)
RX_MAX = re.compile(r'^\s*MAX\s*"([^"]+)"\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_MIN = re.compile(r'^\s*MIN\s*"([^"]+)"\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_DELTA_MAX = re.compile(r'^\s*DELTA[_ ]MAX\s*"([^"]+)"\s*"([^"]+)"(?:\s*PER\s*"([^"]+)")?\s*$', re.IGNORECASE)
RX_DELTA_MIN = re.compile(r'^\s*DELTA[_ ]MIN\s*"([^"]+)"\s*"([^"]+)"(?:\s*PER\s*"([^"]+)")?\s*$', re.IGNORECASE)
RX_WAIT = re.compile(r'^\s*(?:WAIT|SET\s*"(?:WAIT|wait)")\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_PUMP = re.compile(r'^\s*(?:PUMP|SET\s*"(?:PUMP|pump|POMPA|pompa)")\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_SAMPLE = re.compile(r'^\s*SAMPLE\s*"([^"]+)"\s*"(START|STOP)"(?:\s*"([^"]+)")?\s*$', re.IGNORECASE)
RX_CALC = re.compile(r'^\s*CALC\s*"([^"]+)"\s*=\s*"(AVG|SUM|MIN|MAX|COUNT|STDDEV)"\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_FUN = re.compile(r'^\s*FUN\s*"([^"]+)"\s*=\s*(.+)\s*$', re.IGNORECASE)
RX_LOG = re.compile(r'^\s*LOG\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_ALARM = re.compile(r'^\s*ALARM\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_ERROR = re.compile(r'^\s*ERROR\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_SAVE = re.compile(r'^\s*SAVE\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_USER = re.compile(r'^\s*USER\s*"([^"]+)"\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_RESULT = re.compile(r'^\s*RESULT\s*"([^"]+)"\s*$', re.IGNORECASE)
RX_OPT = re.compile(r'^\s*OPT\s*"([^"]+)"\s*(?:"([^"]+)")?', re.IGNORECASE)
RX_INFO = re.compile(r'^\s*INFO\s*"([^"]+)"\s*(?:"([^"]*)")?', re.IGNORECASE)
RX_REPEAT = re.compile(r'^\s*REPEAT\s*$', re.IGNORECASE)
RX_END = re.compile(r'^\s*END\s*$', re.IGNORECASE)
RX_FUNC_CALL_BR = re.compile(r'^\s*FUNC\s*"([^"]+)"((?:\s*(?:"[^"]+"))*)\s*$', re.IGNORECASE)
RX_OUT = re.compile(r'^\s*OUT\s*"([^"]+)"\s*(?:"([^"]*)")?', re.IGNORECASE)
RX_DIALOG = re.compile(r'^\s*DIALOG\s*"([^"]+)"\s*"([^"]*)"', re.IGNORECASE)


def _get_first_defined(*values: str | None) -> str:
    for v in values:
        if v is not None:
            return v
    return ''


def _parse_task_part(s: str) -> dict[str, str] | None:
    mk2 = re.match(r'^\s*"([^"]+)"\s*"([^"]+)"\s*$', s) or re.match(r'^\s*\[([^\]]+)\]\s*\[([^\]]+)\]\s*$', s)
    if mk2:
        return {'function': (mk2.group(1) or '').strip(), 'object': (mk2.group(2) or '').strip()}
    mk_quote = re.match(r'^\s*"([^"]+)"\s*"([^"]*)"\s*$', s) or re.match(r'^\s*\[([^\]]+)\]\s*"([^"]*)"\s*$', s)
    if mk_quote:
        return {'function': (mk_quote.group(1) or '').strip(), 'object': (mk_quote.group(2) or '').strip()}
    mk = re.match(r'^([^\["]+?)(?:\s*(?:\[(.+?)\]|"([^"]*)"))?$', s)
    if mk:
        return {'function': (mk.group(1) or '').strip(), 'object': (mk.group(2) or mk.group(3) or '').strip()}
    return None


def _add_error(errors: list[str], line_num: int, msg: str) -> None:
    errors.append(f'Linia {line_num}: {msg}')


class _ParserState:
    def __init__(self) -> None:
        self.cur_goal: DslGoal | None = None
        self.cur_func: DslFunc | None = None
        self.cur_task: DslTask | None = None


def _parse_goal_line(m: re.Match[str], ast: DslAst, state: _ParserState) -> bool:
    state.cur_goal = DslGoal(name=m.group(1).strip(), tasks=[], conditions=[], steps=[])
    ast.goals.append(state.cur_goal)
    state.cur_func = None
    state.cur_task = None
    return True


def _parse_func_line(ln: str, m: re.Match[str], ast: DslAst, state: _ParserState) -> bool:
    indent_match = re.search(r'\S', ln)
    indent = indent_match.start() if indent_match else 0
    if indent > 0 and state.cur_goal:
        step = {'type': 'func_call', 'name': m.group(1).strip()}
        if state.cur_goal.steps:
            state.cur_goal.steps.append(step)  # type: ignore[arg-type]
        return True
    state.cur_func = DslFunc(name=m.group(1).strip(), tasks=[], steps=[])
    if ast.funcs is None:
        ast.funcs = []
    ast.funcs.append(state.cur_func)
    state.cur_goal = None
    state.cur_task = None
    return True


def _parse_func_call_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'FUNC call bez GOAL/FUNC')
        return False
    func_name = m.group(1).strip()
    args_raw = m.group(2) or ''
    args: list[str] = []
    for am in re.finditer(r'"([^"]+)"|\[([^\]]+)\]', args_raw):
        args.append((am.group(1) or am.group(2) or '').strip())
    step = {'type': 'func_call', 'name': func_name, 'arguments': args}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_task_inline_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'TASK bez GOAL/FUNC')
        return False
    body = m.group(1)
    task_quoted = re.match(r'^\s*\[([^\]]+)\]\s*"([^"]*)"\s*$', body)
    if task_quoted:
        action = task_quoted.group(1).strip()
        value = task_quoted.group(2).strip()
        if action.upper() == 'WAIT':
            step = {'type': 'wait', 'duration': value}
            if cur_block.steps:
                cur_block.steps.append(step)  # type: ignore[arg-type]
            return True
        t = DslTask(function=action, object=value, ands=[])
        cur_block.tasks.append(t)
        if cur_block.steps:
            cur_block.steps.append({'type': 'task', 'function': action, 'object': value, 'ands': []})
        return True
    parts = re.split(r'\bAND\b', body, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        _add_error(errors, line_num, 'Pusta definicja TASK')
        return False
    first = _parse_task_part(parts[0])
    if not first:
        _add_error(errors, line_num, 'Nieprawidłowa akcja w TASK')
        return False
    t = DslTask(function=first['function'], object=first['object'], ands=[])
    for k in range(1, len(parts)):
        mk = _parse_task_part(parts[k])
        if mk:
            t.ands.append(DslTaskAnd(function=mk['function'], object=mk['object']))
        else:
            _add_error(errors, line_num, 'Nieprawidłowa składnia AND')
    cur_block.tasks.append(t)
    if cur_block.steps:
        cur_block.steps.append({'type': 'task', 'function': t.function, 'object': t.object, 'ands': t.ands})
    return True


def _parse_act_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int, state: _ParserState
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'Akcja bez GOAL/FUNC')
        return False
    t = DslTask(
        function=m.group(1).strip(),
        object=_get_first_defined(m.group(2), m.group(3)).strip(),
        ands=[]
    )
    cur_block.tasks.append(t)
    if cur_block.steps:
        cur_block.steps.append({'type': 'task', 'function': t.function, 'object': t.object, 'ands': []})
    state.cur_task = t
    return True


def _parse_and_line(
    m: re.Match[str], cur_task: DslTask | None, errors: list[str], line_num: int
) -> bool:
    if not cur_task:
        _add_error(errors, line_num, 'AND bez poprzedniej akcji')
        return False
    cur_task.ands.append(DslTaskAnd(
        function=m.group(1).strip(),
        object=_get_first_defined(m.group(2), m.group(3)).strip()
    ))
    return True


def _parse_if_compound_or_if_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'IF bez GOAL/FUNC')
        return False
    c1 = DslIfCondition(parameter=m.group(1).strip(), operator=m.group(2), value=m.group(3).strip(), connector='OR')
    if cur_goal:
        cur_goal.conditions.append(c1)
    if cur_block.steps is not None:
        cur_block.steps.append(c1)
    c2 = DslIfCondition(
        parameter=m.group(4).strip(), operator=m.group(5), value=m.group(6).strip(), incomingConnector='OR'
    )
    if cur_goal:
        cur_goal.conditions.append(c2)
    if cur_block.steps is not None:
        cur_block.steps.append(c2)
    return True


def _parse_if_compound_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'IF bez GOAL/FUNC')
        return False
    c1 = DslIfCondition(parameter=m.group(1).strip(), operator=m.group(2), value=m.group(3).strip(), connector='OR')
    if cur_goal:
        cur_goal.conditions.append(c1)
    if cur_block.steps is not None:
        cur_block.steps.append(c1)
    c2 = DslIfCondition(
        parameter=m.group(4).strip(), operator=m.group(5), value=m.group(6).strip(), incomingConnector='OR'
    )
    if cur_goal:
        cur_goal.conditions.append(c2)
    if cur_block.steps is not None:
        cur_block.steps.append(c2)
    return True


def _parse_if_op_str_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'IF bez GOAL/FUNC')
        return False
    c = DslIfCondition(parameter=m.group(1).strip(), operator=m.group(2), value=m.group(3).strip())
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _parse_if_str_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'IF bez GOAL/FUNC')
        return False
    c = DslIfCondition(parameter=m.group(1).strip(), operator='=', value=m.group(2).strip())
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _parse_or_if_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'OR IF bez GOAL/FUNC')
        return False
    op = m.group(2) or '='
    val = m.group(3).strip() if m.group(3) else ''
    c = DslIfCondition(parameter=m.group(1).strip(), operator=op, value=val, incomingConnector='OR')
    if cur_block.steps is not None and cur_block.steps:
        prev = cur_block.steps[-1] if cur_block.steps else None
        if prev and isinstance(prev, DslIfCondition):
            prev.connector = 'OR'
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _parse_if_standard_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        return False
    c = DslIfCondition(parameter=m.group(1).strip(), operator=m.group(2), value=m.group(3).strip())
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _parse_else_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'ELSE bez GOAL/FUNC')
        return False
    c = DslElseCondition(actionType=m.group(1).upper(), actionMessage=m.group(2))
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _parse_else_plain_line(
    cur_goal: DslGoal | None, cur_func: DslFunc | None, errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'ELSE bez GOAL/FUNC')
        return False
    c = DslElseCondition()
    if cur_goal:
        cur_goal.conditions.append(c)
    if cur_block.steps is not None:
        cur_block.steps.append(c)
    return True


def _create_param_step(
    type_: str, m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, f'{type_.upper()} bez GOAL/FUNC')
        return False
    step: dict[str, Any] = {'type': type_, 'parameter': m.group(1).strip()}
    unit = (m.group(2) or '').strip()
    if unit:
        step['unit'] = unit
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_set_quoted_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'SET bez GOAL/FUNC')
        return False
    step = {'type': 'set', 'parameter': m.group(1).strip(), 'value': m.group(2).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_set_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'SET bez GOAL/FUNC')
        return False
    inside = (m.group(2) or '').strip()
    parts = inside.split()
    value = parts[0] or ''
    unit = ' '.join(parts[1:])
    step: dict[str, Any] = {'type': 'set', 'parameter': m.group(1).strip(), 'value': value}
    if unit:
        step['unit'] = unit
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_limit_line(
    type_: Literal['max', 'min'], m: re.Match[str],
    cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, f'{type_.upper()} bez GOAL/FUNC')
        return False
    inside = (m.group(2) or '').strip()
    parts = inside.split()
    value = parts[0] or ''
    unit = ' '.join(parts[1:])
    step: dict[str, Any] = {'type': type_, 'parameter': m.group(1).strip(), 'value': value}
    if unit:
        step['unit'] = unit
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_delta_line(
    type_: Literal['delta_max', 'delta_min'], m: re.Match[str],
    cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, f'{type_.upper().replace("_", "_")} bez GOAL/FUNC')
        return False
    inside = (m.group(2) or '').strip()
    parts = inside.split()
    value = parts[0] or ''
    unit = ' '.join(parts[1:])
    per = (m.group(3) or '').strip()
    step: dict[str, Any] = {'type': type_, 'parameter': m.group(1).strip(), 'value': value}
    if unit:
        step['unit'] = unit
    if per:
        step['per'] = per
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_wait_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'WAIT bez GOAL/FUNC')
        return False
    dur = (m.group(1) or '').strip()
    dur_parts = dur.split()
    step: dict[str, Any] = {'type': 'wait', 'duration': dur_parts[0] or dur}
    if len(dur_parts) > 1:
        step['unit'] = ' '.join(dur_parts[1:])
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_pump_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'PUMP bez GOAL/FUNC')
        return False
    raw = (m.group(1) or '').strip()
    parts = raw.split()
    step: dict[str, Any] = {'type': 'pump', 'raw': raw, 'value': parts[0] or raw}
    if len(parts) > 1:
        step['unit'] = ' '.join(parts[1:])
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_sample_line(
    m: re.Match[str], cur_goal: DslGoal | None, errors: list[str], line_num: int
) -> bool:
    if not cur_goal:
        _add_error(errors, line_num, 'SAMPLE bez GOAL')
        return False
    step: dict[str, Any] = {'type': 'sample', 'parameter': m.group(1).strip(), 'state': m.group(2).upper()}
    if m.group(3):
        step['interval'] = m.group(3).strip()
    if cur_goal.steps is not None:
        cur_goal.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_calc_line(
    m: re.Match[str], cur_goal: DslGoal | None, errors: list[str], line_num: int
) -> bool:
    if not cur_goal:
        _add_error(errors, line_num, 'CALC bez GOAL')
        return False
    step = {
        'type': 'calc',
        'result': m.group(1).strip(),
        'function': m.group(2).upper(),
        'input': m.group(3).strip()
    }
    if cur_goal.steps is not None:
        cur_goal.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_fun_line(
    m: re.Match[str], cur_goal: DslGoal | None, errors: list[str], line_num: int
) -> bool:
    if not cur_goal:
        _add_error(errors, line_num, 'FUN bez GOAL')
        return False
    result = m.group(1).strip()
    expr = m.group(2).strip()
    vars_list: list[str] = []
    for vm in re.finditer(r'"([^"]+)"|\[([^\]]+)\]', expr):
        vars_list.append((vm.group(1) or vm.group(2)).strip())
    step = {'type': 'fun', 'result': result, 'expression': expr, 'variables': vars_list}
    if cur_goal.steps is not None:
        cur_goal.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_simple_line(
    type_: str, m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, f'{type_.upper()} bez GOAL/FUNC')
        return False
    step = {'type': type_, 'message': m.group(1).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_save_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'SAVE bez GOAL/FUNC')
        return False
    step = {'type': 'save', 'parameter': m.group(1).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_user_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'USER bez GOAL/FUNC')
        return False
    step = {'type': 'user', 'action': m.group(1).strip(), 'message': m.group(2).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_result_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'RESULT bez GOAL/FUNC')
        return False
    step = {'type': 'result', 'status': m.group(1).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_opt_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'OPT bez GOAL/FUNC')
        return False
    desc = (m.group(2) or m.group(3) or '').strip()
    step = {'type': 'opt', 'parameter': m.group(1).strip(), 'description': desc}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_info_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'INFO bez GOAL/FUNC')
        return False
    msg = (m.group(2) or m.group(3) or '').strip()
    step = {'type': 'info', 'level': m.group(1).strip().upper(), 'message': msg}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_repeat_line(
    cur_goal: DslGoal | None, cur_func: DslFunc | None, errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'REPEAT bez GOAL/FUNC')
        return False
    step = {'type': 'repeat'}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_end_line(
    cur_goal: DslGoal | None, cur_func: DslFunc | None, errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'END bez GOAL/FUNC')
        return False
    step = {'type': 'end'}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_out_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'OUT bez GOAL/FUNC')
        return False
    out_type = m.group(1).strip().upper()
    out_val = (m.group(2) or m.group(3) or '').strip()
    step = {'type': 'out', 'outType': out_type, 'value': out_val}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


def _parse_dialog_line(
    m: re.Match[str], cur_goal: DslGoal | None, cur_func: DslFunc | None,
    errors: list[str], line_num: int
) -> bool:
    cur_block = cur_goal or cur_func
    if not cur_block:
        _add_error(errors, line_num, 'DIALOG bez GOAL/FUNC')
        return False
    step = {'type': 'dialog', 'parameter': m.group(1).strip(), 'message': m.group(2).strip()}
    if cur_block.steps is not None:
        cur_block.steps.append(step)  # type: ignore[arg-type]
    return True


@dataclass
class _LineCtx:
    ln: str
    normalized: str
    line_num: int
    ast: DslAst
    state: _ParserState
    errors: list[str]


def _try_parse_header(ctx: _LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := RX_SCENARIO.match(ctx.normalized)):
        ctx.ast.scenario = m.group(1).strip()
        return True
    if (m := RX_GOAL.match(ctx.normalized)):
        _parse_goal_line(m, ctx.ast, ctx.state)
        return True
    if (m := RX_FUNC.match(ctx.normalized)):
        _parse_func_line(ctx.ln, m, ctx.ast, ctx.state)
        return True
    if (m := RX_FUNC_CALL_BR.match(ctx.normalized)):
        return _parse_func_call_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_TASK.match(ctx.normalized)):
        if not ctx.state.cur_goal and not ctx.state.cur_func:
            _add_error(ctx.errors, ctx.line_num, 'TASK bez GOAL/FUNC')
            return True
        ctx.state.cur_task = None
        return True
    if (m := RX_TASK_INLINE.match(ctx.normalized)):
        return _parse_task_inline_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_ACT.match(ctx.normalized)):
        return _parse_act_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num, ctx.state)
    if (m := RX_AND.match(ctx.normalized)):
        return _parse_and_line(m, ctx.state.cur_task, ctx.errors, ctx.line_num)
    return False


def _try_parse_if_else(ctx: _LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := RX_IF_COMPOUND_OR_IF.match(ctx.normalized)):
        return _parse_if_compound_or_if_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_IF_COMPOUND.match(ctx.normalized)):
        return _parse_if_compound_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_IF_OP_STR.match(ctx.normalized)):
        return _parse_if_op_str_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_IF_STR.match(ctx.normalized)):
        return _parse_if_str_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_OR_IF.match(ctx.normalized)):
        return _parse_or_if_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_IF_INFIX.match(ctx.normalized)) or (m := RX_IF_BR.match(ctx.normalized)) or (m := RX_IF_PAR.match(ctx.normalized)):
        _parse_if_standard_line(m, ctx.state.cur_goal, ctx.state.cur_func)
        return True
    if (m := RX_ELSE.match(ctx.normalized)):
        return _parse_else_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_ELSE_PLAIN.match(ctx.normalized)):
        return _parse_else_plain_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def _try_parse_declarations(ctx: _LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := RX_GET.match(ctx.normalized)):
        return _create_param_step('get', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_VAL.match(ctx.normalized)):
        return _create_param_step('val', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_SET_QUOTED.match(ctx.normalized)):
        return _parse_set_quoted_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_SET.match(ctx.normalized)):
        return _parse_set_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_MAX.match(ctx.normalized)):
        return _parse_limit_line('max', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_MIN.match(ctx.normalized)):
        return _parse_limit_line('min', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_DELTA_MAX.match(ctx.normalized)):
        return _parse_delta_line('delta_max', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_DELTA_MIN.match(ctx.normalized)):
        return _parse_delta_line('delta_min', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_WAIT.match(ctx.normalized)):
        return _parse_wait_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_PUMP.match(ctx.normalized)):
        return _parse_pump_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def _try_parse_misc_logging(ctx: _LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := RX_LOG.match(ctx.normalized)):
        return _parse_simple_line('log', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_ALARM.match(ctx.normalized)):
        return _parse_simple_line('alarm', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_ERROR.match(ctx.normalized)):
        return _parse_simple_line('error', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_SAVE.match(ctx.normalized)):
        return _parse_save_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_SAMPLE.match(ctx.normalized)):
        return _parse_sample_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    if (m := RX_CALC.match(ctx.normalized)):
        return _parse_calc_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    if (m := RX_FUN.match(ctx.normalized)):
        return _parse_fun_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    return False


def _try_parse_misc_control(ctx: _LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := RX_USER.match(ctx.normalized)):
        return _parse_user_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_RESULT.match(ctx.normalized)):
        return _parse_result_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_OPT.match(ctx.normalized)):
        return _parse_opt_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_INFO.match(ctx.normalized)):
        return _parse_info_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_REPEAT.match(ctx.normalized)):
        return _parse_repeat_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_END.match(ctx.normalized)):
        return _parse_end_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_OUT.match(ctx.normalized)):
        return _parse_out_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := RX_DIALOG.match(ctx.normalized)):
        return _parse_dialog_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def _try_parse_misc(ctx: _LineCtx) -> bool:
    return _try_parse_misc_logging(ctx) or _try_parse_misc_control(ctx)


def _try_parse_line(ctx: _LineCtx) -> bool:
    return (
        _try_parse_header(ctx)
        or _try_parse_if_else(ctx)
        or _try_parse_declarations(ctx)
        or _try_parse_misc(ctx)
    )


def parse_dsl(text: str) -> ParseResult:
    """Parse DSL text into an AST."""
    errors: list[str] = []
    lines = (text or '').split('\n')
    ast = DslAst(scenario='', goals=[], funcs=[])
    state = _ParserState()

    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        normalized_ln = normalize_dsl_text_quotes(ln)
        ctx = _LineCtx(
            ln=ln,
            normalized=normalized_ln,
            line_num=i + 1,
            ast=ast,
            state=state,
            errors=errors,
        )
        if _try_parse_line(ctx):
            continue
        if re.match(r'^\s*#', normalized_ln):
            continue
        if ln.strip():
            errors.append(f'Linia {i + 1}: Nieznana składnia: {ln.strip()}')

    has_content = len(ast.goals) > 0 or (len(ast.funcs) if ast.funcs else 0) > 0
    if not has_content:
        errors.append('Brak sekcji GOAL lub FUNC')

    return ParseResult(ok=has_content, errors=errors, ast=ast)
