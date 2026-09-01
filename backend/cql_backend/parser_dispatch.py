"""DSL line dispatch helpers extracted from parser.py for lower module MI."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from . import parser as p

if TYPE_CHECKING:
    from .types import DslAst


@dataclass
class LineCtx:
    ln: str
    normalized: str
    line_num: int
    ast: DslAst
    state: p._ParserState
    errors: list[str]


def try_parse_header(ctx: LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := p.RX_SCENARIO.match(ctx.normalized)):
        ctx.ast.scenario = m.group(1).strip()
        return True
    if (m := p.RX_GOAL.match(ctx.normalized)):
        p._parse_goal_line(m, ctx.ast, ctx.state)
        return True
    if (m := p.RX_FUNC.match(ctx.normalized)):
        p._parse_func_line(ctx.ln, m, ctx.ast, ctx.state)
        return True
    if (m := p.RX_FUNC_CALL_BR.match(ctx.normalized)):
        return p._parse_func_call_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_TASK.match(ctx.normalized)):
        if not ctx.state.cur_goal and not ctx.state.cur_func:
            p._add_error(ctx.errors, ctx.line_num, 'TASK bez GOAL/FUNC')
            return True
        ctx.state.cur_task = None
        return True
    if (m := p.RX_TASK_INLINE.match(ctx.normalized)):
        return p._parse_task_inline_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_ACT.match(ctx.normalized)):
        return p._parse_act_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num, ctx.state)
    if (m := p.RX_AND.match(ctx.normalized)):
        return p._parse_and_line(m, ctx.state.cur_task, ctx.errors, ctx.line_num)
    return False


def try_parse_if_else(ctx: LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := p.RX_IF_COMPOUND_OR_IF.match(ctx.normalized)):
        return p._parse_if_compound_or_if_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_IF_COMPOUND.match(ctx.normalized)):
        return p._parse_if_compound_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_IF_OP_STR.match(ctx.normalized)):
        return p._parse_if_op_str_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_IF_STR.match(ctx.normalized)):
        return p._parse_if_str_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_OR_IF.match(ctx.normalized)):
        return p._parse_or_if_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_IF_INFIX.match(ctx.normalized)) or (m := p.RX_IF_BR.match(ctx.normalized)) or (m := p.RX_IF_PAR.match(ctx.normalized)):
        p._parse_if_standard_line(m, ctx.state.cur_goal, ctx.state.cur_func)
        return True
    if (m := p.RX_ELSE.match(ctx.normalized)):
        return p._parse_else_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_ELSE_PLAIN.match(ctx.normalized)):
        return p._parse_else_plain_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def try_parse_declarations(ctx: LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := p.RX_GET.match(ctx.normalized)):
        return p._create_param_step('get', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_VAL.match(ctx.normalized)):
        return p._create_param_step('val', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_SET_QUOTED.match(ctx.normalized)):
        return p._parse_set_quoted_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_SET.match(ctx.normalized)):
        return p._parse_set_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_MAX.match(ctx.normalized)):
        return p._parse_limit_line('max', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_MIN.match(ctx.normalized)):
        return p._parse_limit_line('min', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_DELTA_MAX.match(ctx.normalized)):
        return p._parse_delta_line('delta_max', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_DELTA_MIN.match(ctx.normalized)):
        return p._parse_delta_line('delta_min', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_WAIT.match(ctx.normalized)):
        return p._parse_wait_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_PUMP.match(ctx.normalized)):
        return p._parse_pump_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def try_parse_misc_logging(ctx: LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := p.RX_LOG.match(ctx.normalized)):
        return p._parse_simple_line('log', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_ALARM.match(ctx.normalized)):
        return p._parse_simple_line('alarm', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_ERROR.match(ctx.normalized)):
        return p._parse_simple_line('error', m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_SAVE.match(ctx.normalized)):
        return p._parse_save_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_SAMPLE.match(ctx.normalized)):
        return p._parse_sample_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    if (m := p.RX_CALC.match(ctx.normalized)):
        return p._parse_calc_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    if (m := p.RX_FUN.match(ctx.normalized)):
        return p._parse_fun_line(m, ctx.state.cur_goal, ctx.errors, ctx.line_num)
    return False


def try_parse_misc_control(ctx: LineCtx) -> bool:
    m: re.Match[str] | None
    if (m := p.RX_USER.match(ctx.normalized)):
        return p._parse_user_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_RESULT.match(ctx.normalized)):
        return p._parse_result_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_OPT.match(ctx.normalized)):
        return p._parse_opt_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_INFO.match(ctx.normalized)):
        return p._parse_info_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_REPEAT.match(ctx.normalized)):
        return p._parse_repeat_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_END.match(ctx.normalized)):
        return p._parse_end_line(ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_OUT.match(ctx.normalized)):
        return p._parse_out_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    if (m := p.RX_DIALOG.match(ctx.normalized)):
        return p._parse_dialog_line(m, ctx.state.cur_goal, ctx.state.cur_func, ctx.errors, ctx.line_num)
    return False


def try_parse_misc(ctx: LineCtx) -> bool:
    return try_parse_misc_logging(ctx) or try_parse_misc_control(ctx)


def try_parse_line(ctx: LineCtx) -> bool:
    return (
        try_parse_header(ctx)
        or try_parse_if_else(ctx)
        or try_parse_declarations(ctx)
        or try_parse_misc(ctx)
    )
