"""Dedicated map QA; reuse release adapters/config without editing their runner."""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

here = Path(__file__).resolve().parent
repo = here.parents[2]
adapters = here.parent / "release"
out = Path(os.environ.get("SAQ_QA_ARTIFACTS", "/tmp/saq-city-map"))
out.mkdir(parents=True, exist_ok=True)
for port in [8011, 5181]:
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            check.bind(("127.0.0.1", port))
        except OSError:
            sys.exit(f"QA port {port} is in use; stop only your own QA processes.")
env = {
    key: value
    for key, value in os.environ.items()
    if not key.startswith(("FIREBASE_", "GEMINI_", "VITE_"))
    and key != "GOOGLE_APPLICATION_CREDENTIALS"
}
env["PYTHONPATH"] = os.pathsep.join([str(adapters), str(repo / "backend")])
env["SAQ_QA_ARTIFACTS"] = str(out)
backend_python = os.environ.get(
    "SAQ_BACKEND_PYTHON", str(repo / "backend/.venv/bin/python")
)
processes = []
logs = []
with tempfile.TemporaryDirectory(prefix="saq-city-map-") as runtime:
    try:
        for name, command, cwd in [
            (
                "api",
                [
                    backend_python,
                    "-m",
                    "uvicorn",
                    "local_api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                    "--no-access-log",
                ],
                runtime,
            ),
            (
                "vite",
                [
                    "node",
                    "node_modules/vite/bin/vite.js",
                    "--config",
                    "qa/release/vite.config.ts",
                ],
                repo / "frontend",
            ),
        ]:
            logfile = (out / f"{name}.log").open("w")
            logs.append(logfile)
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=logfile,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            )
        for url in ["http://127.0.0.1:8011/api/v1/health", "http://127.0.0.1:5181/"]:
            deadline = time.monotonic() + 30
            while True:
                if any(process.poll() is not None for process in processes):
                    sys.exit(f"QA process exited; see {out}")
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    sys.exit(f"QA readiness timeout; see {out}")
                time.sleep(0.1)
        result = subprocess.run(
            [sys.executable, str(here / "browser_check.py")],
            cwd=repo / "frontend",
            env=env,
        )
        raise SystemExit(result.returncode)
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for logfile in logs:
            logfile.close()
