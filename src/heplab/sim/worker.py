"""Linux supervisor staged by the trusted host adapter; stdlib only.

Cancellation is a shared file so stopping wsl.exe cannot orphan the generator.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    prefix, stage = Path(sys.argv[1]), Path(sys.argv[2])
    timeout = float(sys.argv[3])
    inventory = json.loads((prefix / "heplab-runtime.json").read_text())

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    if digest(prefix / "heplab-explicit.lock") != inventory["explicit_lock_sha256"]:
        raise RuntimeError("runtime lock changed")
    if digest(prefix / "bin/DelphesPythia8") != inventory["driver_sha256"]:
        raise RuntimeError("generator executable changed")
    for name, checksum in inventory["cards_sha256"].items():
        if digest(prefix / "share/delphes/cards" / name) != checksum:
            raise RuntimeError("detector card changed: " + name)
    for name, checksum in inventory.get("physics_inputs_sha256", {}).items():
        if digest(prefix / name) != checksum:
            raise RuntimeError("physics runtime input changed: " + name)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(prefix / "lib")
    env["PYTHIA8DATA"] = str(prefix / "share/Pythia8/xmldoc")
    process = subprocess.Popen(
        [
            str(prefix / "bin/DelphesPythia8"),
            str(stage / "response.tcl"),
            str(stage / "generation.cmnd"),
            str(stage / "events.root"),
        ],
        cwd=prefix,
        env=env,
        start_new_session=True,
    )
    started = time.monotonic()
    try:
        while process.poll() is None:
            if (stage / ".cancel").exists():
                raise RuntimeError("simulation cancelled")
            if time.monotonic() - started > timeout:
                raise RuntimeError("simulation timeout")
            if (stage / "generator.log").stat().st_size > 16 * 1024 * 1024:
                raise RuntimeError("generator log budget exceeded")
            if (stage / "events.root").exists() and (stage / "events.root").stat().st_size > 2**30:
                raise RuntimeError("ROOT output exceeds 1 GiB run budget")
            time.sleep(0.1)
        return process.returncode
    finally:
        if process.poll() is None:
            if sys.platform == "win32":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        (Path(sys.argv[2]) / "worker-error.json").write_text(json.dumps({"error": str(exc)}))
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(2)
