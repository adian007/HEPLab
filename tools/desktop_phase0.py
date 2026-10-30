"""Read-only baseline probes; all new runs live in a fresh evidence directory.

Run capture first, then worker (source and/or --binary), or serve for the
Playwright CLI browser probe. Never point --output at an existing directory.
These are observations, not regression tests asserting that defects are correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def capture(output):
    output.mkdir(parents=True, exist_ok=False)
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, text=True
    )
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True
    ).splitlines()
    paths = set(changed)
    # Also freeze the untracked source/test/doc inputs used by this audit.
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "src", "tests", "docs"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    paths.update(untracked)
    pairs = {
        "workbench.js": (
            "src/heplab/server/static/workbench.js",
            "desktop/frontend/ui/workbench.js",
        ),
        "index.html": ("src/heplab/server/static/index.html", "desktop/frontend/index.html"),
        "workbench.css": (
            "src/heplab/server/static/workbench.css",
            "desktop/frontend/ui/workbench.css",
        ),
    }
    value = {
        "created_utc": datetime.now(UTC).isoformat(),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "status": status,
        "input_sha256": {name: digest(ROOT / name) for name in sorted(paths)},
        "frontend_sha256": {
            name: {"source": digest(ROOT / source), "generated": digest(ROOT / generated)}
            for name, (source, generated) in pairs.items()
        },
        "python": sys.version,
    }
    write_new(output / "baseline.json", value)
    print(json.dumps({"inputs": len(paths), "output": str(output)}))


class Worker:
    def __init__(self, project, binary=None):
        command = [str(binary)] if binary else [sys.executable, "-m", "heplab.desktop.worker"]
        self.process = subprocess.Popen(
            [*command, "--project-root", str(project)],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.lines = queue.Queue()
        self.errors = []

        def read():
            for line in self.process.stdout:
                self.lines.put(line)
            self.lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        threading.Thread(
            target=lambda: self.errors.append(self.process.stderr.read()), daemon=True
        ).start()
        self.hello = self.receive()
        self.identity = 0

    def receive(self):
        line = self.lines.get(timeout=30)
        if line is None:
            raise RuntimeError("worker exited before replying")
        return json.loads(line)

    def call(self, op, **args):
        self.identity += 1
        self.process.stdin.write(json.dumps({"id": self.identity, "op": op, "args": args}) + "\n")
        self.process.stdin.flush()
        reply = self.receive()
        assert reply["id"] == self.identity, reply
        return reply

    def run(self, **config):
        reply = self.call("jobs.submit", config=config)
        if not reply["ok"]:
            return reply
        identity = reply["result"]["id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            reply = self.call("jobs.get", job_id=identity)
            if not reply["ok"] or reply["result"]["status"] not in {"queued", "running"}:
                return reply
            time.sleep(0.05)
        raise TimeoutError("probe job exceeded 60 seconds")

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)
        assert self.process.returncode == 0, self.errors


def probe_worker(output, binary):
    label = "packaged" if binary else "source"
    project = output / f"{label}-project"
    project.mkdir(exist_ok=False)
    worker = Worker(project, binary)
    value = {"hello": worker.hello, "binary_sha256": digest(binary) if binary else None}
    try:
        value["session"] = worker.call("workbench.session")
        value["ideal"] = worker.run(source_model="transverse_pair", response_model="ideal")
        value["response"] = worker.run(
            source_model="transverse_pair", response_model="delphes_reference"
        )
        value["incompatible"] = worker.run(response_model="delphes_reference", momentum_gev=1.0)
        value["runs"] = worker.call("runs.list")
        ideal = value["ideal"]["result"]["result"]
        response = value["response"]["result"]["result"]
        value["response_keeps_transport_and_digits"] = all(
            a["points"] == b["points"]
            and a["material"] == b["material"]
            and a["digit"] == b["digit"]
            for a, b in zip(ideal["tracks"], response["tracks"], strict=True)
        )
        value["run_id"] = value["ideal"]["result"]["id"]
    finally:
        worker.close()
    worker = Worker(project, binary)
    try:
        value["after_restart_list"] = worker.call("runs.list")
        value["after_restart_get"] = worker.call("runs.get", run_id=value["run_id"])
        value["after_restart_job"] = worker.call("jobs.get", job_id=value["run_id"])
    finally:
        worker.close()
    write_new(output / f"{label}-worker.json", value)
    print(
        json.dumps(
            {
                "worker": label,
                "run": value["run_id"],
                "response_separate": value["response_keeps_transport_and_digits"],
                "reopened": value["after_restart_get"]["ok"],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "worker", "serve", "verify-inputs"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--port", type=int, default=8771)
    args = parser.parse_args()
    if args.action == "capture":
        capture(args.output)
    elif args.action == "worker":
        probe_worker(args.output, args.binary)
    elif args.action == "verify-inputs":
        baseline = json.loads((args.output / "baseline.json").read_text(encoding="utf-8"))
        changed = [
            name
            for name, before in baseline["input_sha256"].items()
            if digest(ROOT / name) != before
        ]
        write_new(args.output / "input-verification.json", {"changed": changed})
        print(json.dumps({"changed": changed}))
        return bool(changed)
    else:
        sys.path.insert(0, str(ROOT / "src"))
        import uvicorn

        from heplab.server.app import create_app

        # This directory belongs to this probe; old artifacts are never touched.
        uvicorn.run(
            create_app(args.output / "browser-project" / "artifacts"),
            host="127.0.0.1",
            port=args.port,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
