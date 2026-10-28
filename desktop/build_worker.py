"""Freeze the Python worker into a Tauri sidecar and smoke-test the handshake.

Run on each native release runner: python desktop/build_worker.py
Requires PyInstaller in the build environment only; the result needs no system Python.
Output: desktop/src-tauri/binaries/heplab-worker-<rust host triple>[.exe]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
ROOT = DESKTOP.parent


def host_triple() -> str:
    output = subprocess.check_output(["rustc", "-vV"], text=True)
    return next(line.split(": ", 1)[1] for line in output.splitlines() if line.startswith("host:"))


def smoke(binary: Path) -> dict:
    """Handshake plus one call, from an empty project, with no PYTHONPATH."""
    with tempfile.TemporaryDirectory() as project:
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        result = subprocess.run(
            [str(binary), "--project-root", project],
            input=json.dumps({"id": 1, "op": "runs.list", "args": {}}) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
            check=True,
        )
    hello, reply = (json.loads(line) for line in result.stdout.splitlines())
    if hello["protocol"] != "heplab-desktop-ipc-v1" or reply != {"id": 1, "ok": True, "result": []}:
        raise SystemExit(f"worker smoke test failed: {hello} {reply}")
    return hello


def main() -> int:
    triple = host_triple()
    suffix = ".exe" if sys.platform == "win32" else ""
    with tempfile.TemporaryDirectory() as work:
        entry = Path(work) / "heplab_worker_entry.py"
        entry.write_text(
            "import sys\nfrom heplab.desktop.worker import main\nsys.exit(main())\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--onefile",
                "--noconfirm",
                "--clean",
                "--name",
                "heplab-worker",
                "--collect-data",
                "heplab",
                "--distpath",
                str(Path(work) / "dist"),
                "--workpath",
                str(Path(work) / "build"),
                "--specpath",
                work,
                str(entry),
            ],
            check=True,
        )
        built = Path(work) / "dist" / f"heplab-worker{suffix}"
        target = DESKTOP / "src-tauri" / "binaries" / f"heplab-worker-{triple}{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, target)
    hello = smoke(target)
    print(json.dumps({"sidecar": str(target.relative_to(ROOT)), "triple": triple, **hello}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
