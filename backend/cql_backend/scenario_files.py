"""HTTP routes for listing, reading, and saving local OQL scenarios."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .api_models import TextIn

router = APIRouter(prefix="/api/cql/scenario-files", tags=["files"])


def get_scenarios_dir() -> Path:
    return Path(os.environ.get("SCENARIOS_DIR", "/app/scenarios"))


def _scenario_path(filename: str) -> tuple[Path, Path]:
    scenarios_dir = get_scenarios_dir()
    file_path = scenarios_dir / filename
    if not file_path.resolve().is_relative_to(scenarios_dir.resolve()):
        raise HTTPException(status_code=403, detail={"error": "invalid filename"})
    return scenarios_dir, file_path


@router.get("")
async def list_scenario_files() -> dict[str, object]:
    scenarios_dir = get_scenarios_dir()
    if not scenarios_dir.exists():
        return {"files": [], "count": 0, "directory": str(scenarios_dir)}

    files = []
    for file_path in sorted(scenarios_dir.glob("*.oql")):
        stat = file_path.stat()
        files.append(
            {
                "name": file_path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "path": str(file_path.relative_to(scenarios_dir)),
            }
        )
    return {
        "files": files,
        "count": len(files),
        "directory": str(scenarios_dir),
    }


@router.get("/{filename}")
async def get_scenario_file(filename: str) -> FileResponse:
    _, file_path = _scenario_path(filename)
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": "file not found", "filename": filename},
        )
    return FileResponse(file_path, media_type="text/plain", filename=filename)


@router.post("/{filename}")
async def save_scenario_file(filename: str, content: TextIn) -> dict[str, str]:
    _, file_path = _scenario_path(filename)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content.text, encoding="utf-8")
    return {"status": "saved", "filename": filename, "path": str(file_path)}
