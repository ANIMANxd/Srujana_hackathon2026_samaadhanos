"""Run the whole demo loop: API (:8000), mock providers (:8100), frontend (:3000).

`make dev` calls this. It exists because the Makefile must stay shell-agnostic (its
header forbids `&`, `$$` and continuations), and three concurrent processes need a
launcher, not a recipe.

Ctrl-C stops all three. A child that exits on its own is reported and the others keep
running, so a crashed frontend does not kill the API mid-demo.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMANDS: list[tuple[str, list[str]]] = [
    ("api", [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", "8000", "--app-dir", str(ROOT)]),
    ("mock", [sys.executable, "-m", "uvicorn", "mock_providers.app:app", "--port", "8100", "--app-dir", str(ROOT)]),
]

FRONTEND = ("frontend", ["npm", "--prefix", str(ROOT / "frontend"), "run", "dev"])


def _spawn(name: str, command: list[str], env: dict[str, str]):
    print(f"[dev] starting {name}: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, cwd=str(ROOT), env=env)


def main() -> int:
    env = dict(os.environ)
    env.setdefault("APP_ENV", "development")
    env.setdefault("PROVIDER_MODE", "mock")
    env.setdefault("MOCK_CLOCK", "1")
    env.setdefault("API_BASE_URL", "http://127.0.0.1:8000")
    env.setdefault("DATABASE_URL", "sqlite:///./data/samadhaan.db")

    include_frontend = "--no-frontend" not in sys.argv
    commands = list(COMMANDS)
    if include_frontend:
        commands.append(FRONTEND)

    processes = []
    try:
        for name, command in commands:
            processes.append((name, _spawn(name, command, env)))
        print("[dev] api http://127.0.0.1:8000/docs | mock http://127.0.0.1:8100/docs", flush=True)
        while True:
            for name, process in processes:
                code = process.poll()
                if code is not None:
                    print(f"[dev] {name} exited with {code}", flush=True)
                    processes = [(n, p) for (n, p) in processes if p.poll() is None]
                    if not processes:
                        return code or 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[dev] stopping", flush=True)
        return 0
    finally:
        for name, process in processes:
            if process.poll() is None:
                try:
                    process.send_signal(signal.SIGTERM)
                except Exception:  # noqa: BLE001 - best effort on Windows
                    process.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
