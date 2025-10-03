from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
import responses

from sanctions_pipeline import build as build_mod
from sanctions_pipeline import validate as validate_mod


def test_build_command_defaults(tmp_path: Path) -> None:
    config = build_mod.SanctionsBuildConfig(
        datasets=("sanctions", "us_ofac"),
        export_path=tmp_path / "export.tar.gz",
        cache_path=tmp_path / "cache",
        release="latest",
        zavod_bin="zavod",
        extra_args=("--dry-run",),
    )
    cmd = build_mod.build_command(config)
    assert cmd[0].endswith("zavod")
    assert cmd[1:3] == ["crawl", "sanctions"]
    assert "--export" in cmd
    assert "--cache" in cmd
    assert "--release" in cmd
    assert cmd[-1] == "--dry-run"


def test_run_build_invokes_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, check, env):
        captured["command"] = command
        captured["check"] = check
        captured["env"] = env
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(build_mod.subprocess, "run", fake_run)
    config = build_mod.SanctionsBuildConfig(export_path=tmp_path / "out/export.tar.gz")
    build_mod.run_build(config)
    assert captured["check"] is True
    assert "--export" in captured["command"]
    assert isinstance(captured["env"], dict)


@responses.activate
def test_yente_smoke_tester_success() -> None:
    base_url = "http://yente.test"
    responses.add(
        responses.GET,
        f"{base_url}/entities/NKC-6CU9E6R4-8",
        json={"id": "NKC-6CU9E6R4-8"},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{base_url}/search",
        json={"results": []},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{base_url}/match",
        json={"matches": []},
        status=200,
    )

    config = validate_mod.SmokeTestConfig(base_url=base_url, api_key="secret")
    tester = validate_mod.YenteSmokeTester(config)
    payload = tester.run()
    assert payload["entity"]["id"] == "NKC-6CU9E6R4-8"
    assert payload["search"]["results"] == []
    assert payload["match"]["matches"] == []
    for call in responses.calls:
        assert call.request.headers.get("X-API-KEY") == "secret"

