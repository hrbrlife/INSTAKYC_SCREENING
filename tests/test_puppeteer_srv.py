import os
import subprocess
import time
import httpx


def test_web_search_creates_artifact(tmp_path):
    webshot_dir = tmp_path / "webshot"
    env = {
        "PUPPETEER_HEADLESS": "true",
        "REDIS_URL": "redis://redis:6379/0",
        "WEBSHOT_DIR": str(webshot_dir),
        "PORT": "7010",
    }
    proc = subprocess.Popen(
        ["node", "docker/puppeteer/server.js"],
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # give server time to start
        time.sleep(0.5)
        resp = httpx.get("http://localhost:7010/search", params={"q": "acme"})
        assert resp.status_code == 200
        assert resp.json() == {"articles": [], "query": "acme"}
        files = list(webshot_dir.glob("*.txt"))
        assert len(files) == 1
    finally:
        proc.terminate()
        proc.wait()


def test_cleanup_removes_old_files(tmp_path):
    old_dir = tmp_path / "shots"
    old_dir.mkdir()
    old_file = old_dir / "old.txt"
    old_file.write_text("old")
    past = time.time() - 600
    os.utime(old_file, (past, past))
    new_file = old_dir / "new.txt"
    new_file.write_text("new")
    subprocess.run(["node", "docker/puppeteer/cleanup.js", str(old_dir)], check=True)
    assert not old_file.exists()
    assert new_file.exists()
