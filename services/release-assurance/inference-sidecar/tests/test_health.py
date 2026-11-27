"""Task 1.1 smoke tests: the context starts alone and its contracted health route returns 200."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from fastapi.testclient import TestClient

from app.release_assurance.main import HEALTH_PATH, app

SERVICE_DIR = Path(__file__).resolve().parents[1]


def test_health_route_returns_up_in_process():
    response = TestClient(app).get(HEALTH_PATH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "up", "context": "release-assurance"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_service_starts_alone_and_reports_healthy():
    """Starts the real uvicorn process with no other context, database, broker, or Vault running."""
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DATABASE", "KAFKA", "VAULT", "REDIS"))}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.release_assurance.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=SERVICE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{HEALTH_PATH}", timeout=2) as resp:
                    assert resp.status == 200
                    assert json.loads(resp.read()) == {"status": "up", "context": "release-assurance"}
                    break
            except OSError:
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise AssertionError(f"service did not become healthy: {proc.stdout.read().decode(errors='replace') if proc.poll() is not None else 'timeout'}")
                time.sleep(0.2)
    finally:
        proc.terminate()
        proc.wait(timeout=15)
