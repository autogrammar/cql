"""Python port of `oqlos/cql/runtime/dsl-scenario-builders.ts`.

DSL builders for different scenario types.
"""
from __future__ import annotations

from typing import Any

from .quotes import format_dsl_literal
from .scenario_dsl_parts import (
    criteria_dsl_lines,
    criteria_goal_conditions,
    goal_dsl_lines,
)


def _q(value: str) -> str:
    return format_dsl_literal(value)


class DslScenarioBuilders:
    """Build DSL from different scenario sources."""

    @staticmethod
    def build_dsl_from_test_scenario(sc: dict[str, Any]) -> str:
        """Build DSL from TestScenario for device testing."""
        lines: list[str] = []
        name = sc.get('name') or 'Unnamed'
        lines.append(f'SCENARIO: {name}')
        lines.append('')
        for act in sc.get('activities') or []:
            act_name = act.get('name') or 'Unnamed'
            lines.append(f'GOAL: {act_name}')
            lines.append(f'  SET {_q(act_name)} {_q("1")}')
            c = act.get('criteria') or {}
            unit = c.get('unit') or ''
            param = unit if unit else act_name
            lines.extend(criteria_dsl_lines(c, param, unit))
            lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def build_goals_from_test_scenario(sc: dict[str, Any]) -> list[dict[str, Any]]:
        """Build goals JSON from TestScenario."""
        goals: list[dict[str, Any]] = []
        for act in sc.get('activities') or []:
            c = act.get('criteria') or {}
            unit = c.get('unit') or ''
            param = unit if unit else act.get('name', '')
            goals.append({
                'name': act.get('name', ''),
                'tasks': [{'function': 'Sprawdź', 'object': act.get('name', '')}],
                'conditions': criteria_goal_conditions(c, param, unit),
            })
        return goals

    @staticmethod
    def build_dsl_from_generic_scenario(scenario: dict[str, Any]) -> str:
        """Build DSL from generic scenario content."""
        lines: list[str] = []
        name = scenario.get('name') if isinstance(scenario, dict) else 'Generic Scenario'
        lines.append(f'SCENARIO: {name}')
        lines.append('')

        goals = scenario.get('goals') or [] if isinstance(scenario, dict) else []
        for goal in goals:
            lines.extend(goal_dsl_lines(goal))

        return '\n'.join(lines)
