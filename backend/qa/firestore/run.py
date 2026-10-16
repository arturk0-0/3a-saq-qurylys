"""Start an isolated Firestore emulator, run SDK integration tests, stop owned processes.

Linux QA tooling only; ordinary app startup never requires an emulator.
"""

import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
REPO = BACKEND.parent
FIREBASE_TOOLS = "15.34.0"


def child_environment(runtime: Path) -> dict[str, str]:
    # Keep network trust/proxy configuration for downloading official tooling.
    # Do not pass application configuration, ADC, tokens or cloud project selection.
    allowed = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "JAVA_HOME",
        "SSL_CERT_FILE",
        "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    no_proxy = "127.0.0.1,localhost," + env.get("NO_PROXY", env.get("no_proxy", ""))
    env.update(
        {
            "NO_PROXY": no_proxy,
            "no_proxy": no_proxy,
            "XDG_CONFIG_HOME": str(runtime / "cli-config"),
            "FIREBASE_EMULATORS_PATH": str(Path(tempfile.gettempdir()) / "saq-firebase-emulators"),
            "npm_config_cache": str(Path(tempfile.gettempdir()) / "saq-npm-cache"),
            "FIREBASE_CLI_DISABLE_UPDATE_CHECK": "true",
            "CI": "true",
            "SAQ_FIRESTORE_INTEGRATION": "1",
        }
    )
    return env


def main() -> int:
    python = BACKEND / ".venv/bin/python"
    if not python.is_file() or not shutil.which("npm") or not shutil.which("java"):
        print("Install backend lockfile dependencies, Node/npm and Java 21+; see QA README.")
        return 2
    runtime = Path(tempfile.mkdtemp(prefix="saq-firestore-integration-"))
    # Reserve distinct free ports during configuration, then let the CLI bind them.
    sockets = [socket.socket() for _ in range(4)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        firestore_port, hub_port, logging_port, ws_port = [s.getsockname()[1] for s in sockets]
    finally:
        for sock in sockets:
            sock.close()
    config = {
        "firestore": {"rules": str(REPO / "firestore.rules")},
        "emulators": {
            "firestore": {"host": "127.0.0.1", "port": firestore_port, "websocketPort": ws_port},
            "hub": {"host": "127.0.0.1", "port": hub_port},
            "logging": {"host": "127.0.0.1", "port": logging_port},
            "ui": {"enabled": False},
            "singleProjectMode": False,
        },
    }
    config_path = runtime / "firebase.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    env = child_environment(runtime)
    # The CLI sets FIRESTORE_EMULATOR_HOST for its child. Tests validate it again.
    test_command = shlex.join(
        [
            str(python),
            "-m",
            "pytest",
            str(BACKEND / "integration_tests"),
            "--rootdir",
            str(BACKEND),
            "-q",
            "-ra",
            f"--junitxml={runtime / 'results.xml'}",
        ]
    )
    command = [
        "npm",
        "exec",
        "--yes",
        "--package",
        f"firebase-tools@{FIREBASE_TOOLS}",
        "--",
        "firebase",
        "emulators:exec",
        "--only",
        "firestore",
        "--project",
        "demo-saq-it-runner",
        "--config",
        str(config_path),
        test_command,
    ]
    print(f"Local emulator QA artifacts: {runtime}", flush=True)
    process = subprocess.Popen(command, cwd=runtime, env=env, start_new_session=True)
    try:
        return process.wait(timeout=600)
    except KeyboardInterrupt:
        return 130
    except subprocess.TimeoutExpired:
        print("Local integration deadline exceeded; stopping only this runner's processes.")
        return 124
    finally:
        # Also clean up Java children after failed CLI startup or an interrupted test.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
