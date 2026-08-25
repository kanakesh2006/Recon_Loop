"""ReconLoop dev runner: starts the FastAPI backend and Vite frontend together.

Ctrl+C terminates both process trees (including npm's node children on Windows).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.api.main:app",
        "--reload",
        "--port",
        "8000",
    ]
    frontend_cmd = ["npm", "run", "dev", "--prefix", str(PROJECT_ROOT / "frontend")]

    processes: list[subprocess.Popen] = []
    try:
        processes.append(subprocess.Popen(backend_cmd, cwd=PROJECT_ROOT))
        processes.append(
            subprocess.Popen(
                frontend_cmd,
                cwd=str(PROJECT_ROOT / "frontend"),
                shell=(os.name == "nt"),
            )
        )
        print("ReconLoop dev servers starting:")
        print("  backend:  http://localhost:8000  (API docs at /docs)")
        print("  frontend: http://localhost:5173")
        print("Press Ctrl+C to stop both.")
        for process in processes:
            process.wait()
    except KeyboardInterrupt:
        print("\nShutting down both servers...")
    finally:
        for process in processes:
            _terminate(process)
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
