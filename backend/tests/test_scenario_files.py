"""Integration tests for the extracted scenario-file router."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from cql_backend.app import app
from cql_backend.scenario_files import _scenario_path


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SCENARIOS_DIR", str(tmp_path))
    return TestClient(app)


def test_scenario_files_list_read_and_save(client: TestClient, tmp_path: Path) -> None:
    (tmp_path / "existing.oql").write_text("VERSION: 6\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("ignored", encoding="utf-8")

    listing = client.get("/api/cql/scenario-files")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["files"][0]["name"] == "existing.oql"

    source = client.get("/api/cql/scenario-files/existing.oql")
    assert source.status_code == 200
    assert source.text == "VERSION: 6\n"

    saved = client.post(
        "/api/cql/scenario-files/new.oql",
        json={"text": "VERSION: 6\nTASK:\n  NAME 'Smoke'\n"},
    )
    assert saved.status_code == 200
    assert (tmp_path / "new.oql").read_text(encoding="utf-8").startswith("VERSION: 6")


def test_scenario_file_missing_returns_404(client: TestClient) -> None:
    response = client.get("/api/cql/scenario-files/missing.oql")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "file not found"


def test_scenario_path_rejects_parent_traversal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SCENARIOS_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as caught:
        _scenario_path("../escape.oql")

    assert caught.value.status_code == 403
