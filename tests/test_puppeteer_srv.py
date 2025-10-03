import json
import os
import subprocess
import time
from pathlib import Path

import httpx


def ensure_node_modules():
    node_modules = Path("docker/puppeteer/node_modules")
    if node_modules.exists():
        return
    subprocess.run(
        ["npm", "ci", "--omit=dev"],
        cwd="docker/puppeteer",
        check=True,
    )


def wait_for_server(base_url: str, headers=None, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/healthz", headers=headers, timeout=0.5)
            if resp.status_code in (200, 503):
                if resp.status_code == 200:
                    return
        except httpx.RequestError:
            pass
        time.sleep(0.1)
    raise TimeoutError("service did not become ready")


def wait_for_completion(job_id: str, base_url: str, headers=None, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = httpx.get(f"{base_url}/tasks/{job_id}", headers=headers, timeout=2.0)
        if resp.status_code != 200:
            time.sleep(0.1)
            continue
        payload = resp.json()
        if payload.get("state") == "completed":
            return payload
        if payload.get("state") == "failed":
            raise AssertionError(f"job failed: {payload}")
        time.sleep(0.1)
    raise TimeoutError("job did not complete in time")


def test_web_search_generates_artifacts(tmp_path):
    webshot_dir = tmp_path / "webshot"
    env = {
        "PUPPETEER_HEADLESS": "true",
        "REDIS_URL": "memory://tests",
        "WEBSHOT_DIR": str(webshot_dir),
        "PORT": "7010",
        "PUPPETEER_FAKE_MODE": "1",
        "SERVICE_TOKEN": "test_worker_token",
    }
    ensure_node_modules()
    proc = subprocess.Popen(
        ["node", "docker/puppeteer/server.js"],
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = "http://localhost:7010"
    headers = {"X-Service-Token": "test_worker_token"}
    try:
        wait_for_server(base_url, headers=headers)
        submit = httpx.post(
            f"{base_url}/tasks",
            json={"query": "acme corp"},
            headers=headers,
            timeout=2.0,
        )
        assert submit.status_code == 202
        job_id = submit.json()["id"]
        result = wait_for_completion(job_id, base_url, headers=headers)
        assert result["result"]["query"] == "acme corp"
        artifacts = result["result"]["artifacts"]
        assert (webshot_dir / artifacts["html"]).exists()
        screenshot = webshot_dir / artifacts["screenshot"]
        assert screenshot.exists()
        assert screenshot.read_bytes().startswith(b"\x89PNG")
        summary = json.loads((webshot_dir / artifacts["summary"]).read_text())
        assert summary["articles"][0]["title"].startswith("Placeholder")
        html = (webshot_dir / artifacts["html"]).read_text()
        assert "Placeholder adverse media result." in html
    finally:
        proc.terminate()
        proc.wait()


def test_cleanup_respects_retention(tmp_path):
    old_dir = tmp_path / "shots"
    old_dir.mkdir()
    old_file = old_dir / "old.txt"
    old_file.write_text("old")
    old_time = time.time() - 7200  # 2 hours ago
    os.utime(old_file, (old_time, old_time))
    new_file = old_dir / "new.txt"
    new_file.write_text("new")
    subprocess.run(
        ["node", "docker/puppeteer/cleanup.js", str(old_dir)],
        env={**os.environ, "ARTIFACT_RETENTION_HOURS": "1"},
        check=True,
    )
    assert not old_file.exists()
    assert new_file.exists()
