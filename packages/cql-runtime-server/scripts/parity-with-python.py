#!/usr/bin/env python3
"""Run golden/cases.json against Python cql-backend and print JSON for diff.

Usage:
  CQL_BACKEND_SRC=/path/to/c2004/connect-scenario/cql-backend \\
    python3 scripts/parity-with-python.py

Exit 0 when all cases pass; 1 on mismatch.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _plan_kinds(plan: list[Any]) -> list[str]:
    kinds: list[str] = []
    for step in plan or []:
        if isinstance(step, dict):
            kinds.append(str(step.get("kind", "")))
        else:
            kinds.append(str(getattr(step, "kind", "")))
    return kinds


def _last_task(plan: list[Any]) -> dict[str, Any] | None:
    for step in reversed(plan or []):
        if isinstance(step, dict):
            if step.get("kind") == "task":
                task = step.get("task")
                return task if isinstance(task, dict) else None
        elif getattr(step, "kind", None) == "task":
            task = getattr(step, "task", None)
            if isinstance(task, dict):
                return task
    return None


def _task_get(task: dict[str, Any], key: str) -> Any:
    return task.get(key)


def _load_backend():
    root = Path(
        os.environ.get(
            "CQL_BACKEND_SRC",
            "/home/tom/github/maskservice/c2004/connect-scenario/cql-backend",
        )
    )
    if not root.is_dir():
        raise SystemExit(f"cql-backend not found: {root}")
    sys.path.insert(0, str(root))
    from cql_backend.exec_runtime import execute_dsl  # noqa: WPS433
    from cql_backend.parser import parse_dsl  # noqa: WPS433
    from cql_backend.quotes import (  # noqa: WPS433
        normalize_dsl_text_quotes,
        quote_dsl_value,
    )
    from cql_backend.validator import validate_dsl_format  # noqa: WPS433

    return {
        "quote": lambda body: {"quoted": quote_dsl_value(body.get("value"))},
        "normalize": lambda body: {"text": normalize_dsl_text_quotes(str(body.get("text", "")))},
        "exec": lambda body: _exec_payload(execute_dsl(str(body.get("text", "")))),
        "parse": lambda body: _parse_payload(parse_dsl(str(body.get("text", "")))),
        "validate": lambda body: _validate_payload(validate_dsl_format(str(body.get("text", "")))),
    }


def _exec_payload(result) -> dict[str, Any]:
    plan = result.plan or []
    return {
        "ok": result.ok,
        "plan": [p if isinstance(p, dict) else p.model_dump(by_alias=True) for p in plan],
        "ast": result.ast.model_dump(by_alias=True) if result.ast else None,
    }


def _parse_payload(result) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "ast": result.ast.model_dump(by_alias=True) if result.ast else None,
    }


def _validate_payload(result) -> dict[str, Any]:
    return {"ok": result.ok}


def _check_ok(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "ok" not in expect or body.get("ok") == expect["ok"]:
        return []
    return [f"ok expected {expect['ok']} got {body.get('ok')}"]


def _check_quoted(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "quoted" not in expect or body.get("quoted") == expect["quoted"]:
        return []
    return ["quoted mismatch"]


def _check_text(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "text" not in expect or body.get("text") == expect["text"]:
        return []
    return ["text mismatch"]


def _check_plan_kinds(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "planKinds" not in expect:
        return []
    kinds = _plan_kinds(body.get("plan") or [])
    if kinds == expect["planKinds"]:
        return []
    return [f"planKinds expected {expect['planKinds']} got {kinds}"]


def _check_plan_kinds_includes(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "planKindsIncludes" not in expect:
        return []
    kinds = _plan_kinds(body.get("plan") or [])
    return [f"missing plan kind {kind}" for kind in expect["planKindsIncludes"] if kind not in kinds]


def _check_scenario(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "scenario" not in expect:
        return []
    ast = body.get("ast") or {}
    if ast.get("scenario") == expect["scenario"]:
        return []
    return [f"scenario expected {expect['scenario']} got {ast.get('scenario')}"]


def _check_last_task(expect: dict[str, Any], body: dict[str, Any]) -> list[str]:
    if "lastTask" not in expect:
        return []
    task = _last_task(body.get("plan") or [])
    if not task:
        return ["lastTask missing"]
    return [
        f"lastTask.{key} mismatch"
        for key, value in expect["lastTask"].items()
        if _task_get(task, key) != value
    ]


_EXPECT_CHECKS = (
    _check_ok,
    _check_quoted,
    _check_text,
    _check_plan_kinds,
    _check_plan_kinds_includes,
    _check_scenario,
    _check_last_task,
)


def _check_case(case: dict[str, Any], body: dict[str, Any]) -> list[str]:
    expect = case.get("expect") or {}
    errors: list[str] = []
    for checker in _EXPECT_CHECKS:
        errors.extend(checker(expect, body))
    return errors


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    cases_path = here / "tests" / "golden" / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    handlers = _load_backend()

    failures: list[str] = []
    for case in cases:
        endpoint = str(case["endpoint"])
        handler = handlers.get(endpoint)
        if not handler:
            failures.append(f"{case['id']}: unknown endpoint {endpoint}")
            continue
        body = handler(case.get("body") or {})
        errors = _check_case(case, body)
        if errors:
            failures.append(f"{case['id']}: " + "; ".join(errors))

    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({"ok": True, "cases": len(cases)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
