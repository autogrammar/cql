"""Small DSL line builders extracted from scenario_builders for lower CC."""
from __future__ import annotations

from typing import Any

from .content_helpers import render_legacy_task_as_dsl_lines
from .quotes import format_dsl_literal


def _q(value: str) -> str:
    return format_dsl_literal(value)


def criteria_dsl_lines(criteria: dict[str, Any], param: str, unit: str) -> list[str]:
    """Emit IF lines for test-scenario activity criteria."""
    lines: list[str] = []
    if criteria.get('min') is not None:
        val = f"{criteria['min']}{f' {unit}' if unit else ''}"
        lines.append(f'  IF {_q(param)} >= {_q(val)}')
    if criteria.get('max') is not None:
        val = f"{criteria['max']}{f' {unit}' if unit else ''}"
        lines.append(f'  IF {_q(param)} <= {_q(val)}')
    if criteria.get('targetValue') is not None:
        val = f"{criteria['targetValue']}{f' {unit}' if unit else ''}"
        lines.append(f'  IF {_q(param)} = {_q(val)}')
    if criteria.get('duration') is not None:
        lines.append(f'  IF {_q("czas")} >= {_q(f"{criteria["duration"]} s")}')
    return lines


def criteria_goal_conditions(criteria: dict[str, Any], param: str, unit: str) -> list[dict[str, Any]]:
    """Build goal JSON conditions from test-scenario activity criteria."""
    result = 'test zaliczony'
    conditions: list[dict[str, Any]] = []
    if criteria.get('min') is not None:
        conditions.append({
            'type': 'if',
            'parameter': param,
            'operator': '>=',
            'value': str(criteria['min']),
            'unit': unit,
            'result': result,
        })
    if criteria.get('max') is not None:
        conditions.append({
            'type': 'if',
            'parameter': param,
            'operator': '<=',
            'value': str(criteria['max']),
            'unit': unit,
            'result': result,
        })
    if criteria.get('targetValue') is not None:
        conditions.append({
            'type': 'if',
            'parameter': param,
            'operator': '=',
            'value': str(criteria['targetValue']),
            'unit': unit,
            'result': result,
        })
    if criteria.get('duration') is not None:
        conditions.append({
            'type': 'if',
            'parameter': 'czas',
            'operator': '>=',
            'value': str(criteria['duration']),
            'unit': 's',
            'result': result,
        })
    return conditions


def variable_dsl_line(variable: dict[str, Any]) -> str | None:
    """Render one variable assignment as a DSL line, or None when skipped."""
    action = str(variable.get('action') or 'GET').upper()
    param = str(variable.get('parameter') or '')
    val = str(variable.get('value') or '').strip()
    unit = str(variable.get('unit') or '').strip()
    if not param:
        return None
    if action in ('GET', 'VAL'):
        unit_part = f' {_q(unit)}' if unit else ''
        return f'  {action} {_q(param)}{unit_part}'
    right = f'{val} {unit}' if unit else val
    return f'  {action} {_q(param)} {_q(right)}'


def condition_dsl_line(condition: dict[str, Any]) -> str | None:
    """Render one goal condition as a DSL line, or None when unsupported."""
    kind = str(condition.get('type') or '').lower()
    if kind == 'if':
        unit = str(condition.get('unit') or '').strip()
        val = str(condition.get('value') or '').strip()
        val_text = f'{val} {unit}' if unit else val
        return (
            f'  IF {_q(condition.get("parameter") or "")} '
            f'{condition.get("operator", "=")} {_q(val_text)}'
        )
    if kind == 'else':
        action_type = str(condition.get('actionType') or 'ERROR').upper()
        action_message = str(condition.get('actionMessage') or '')
        return f'  ELSE {action_type} {_q(action_message)}'
    return None


def _goal_task_lines(goal: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for task in goal.get('tasks') or [] if isinstance(goal, dict) else []:
        if isinstance(task, dict) and task.get('function') and task.get('object'):
            lines.extend(render_legacy_task_as_dsl_lines(task, '  '))
    return lines


def _goal_variable_lines(goal: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for var_group in goal.get('variables') or [] if isinstance(goal, dict) else []:
        vars_list = var_group.get('variables') or [] if isinstance(var_group, dict) else []
        for variable in vars_list:
            if not isinstance(variable, dict):
                continue
            line = variable_dsl_line(variable)
            if line:
                lines.append(line)
    return lines


def _goal_condition_lines(goal: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for condition in goal.get('conditions') or [] if isinstance(goal, dict) else []:
        if not isinstance(condition, dict):
            continue
        line = condition_dsl_line(condition)
        if line:
            lines.append(line)
    return lines


def goal_dsl_lines(goal: dict[str, Any]) -> list[str]:
    """Render one generic scenario goal as DSL lines."""
    goal_name = goal.get('name') if isinstance(goal, dict) else 'GOAL'
    lines = [f'GOAL: {goal_name}']
    lines.extend(_goal_task_lines(goal))
    lines.extend(_goal_variable_lines(goal))
    lines.extend(_goal_condition_lines(goal))
    lines.append('')
    return lines
