"""Misbehaving worker for supervisor tests: python fake_worker.py MODE --project-root DIR."""

import json
import sys
import time
from pathlib import Path

SPEC = json.loads(
    (Path(__file__).resolve().parents[3] / "src/heplab/desktop/operations.json").read_text()
)
mode = sys.argv[1]
hello = {
    "protocol": SPEC["protocol"],
    "worker_version": "test-1",
    "operations": sorted(SPEC["operations"]),
}
if mode == "bad_version":
    hello["worker_version"] = "other"
if mode == "bad_protocol":
    hello["protocol"] = "something-else"
if mode == "silent":
    time.sleep(60)
if mode == "grandchild":
    # Like a PyInstaller bootloader: the real work runs in a child process.
    import subprocess

    beat = Path(sys.argv[sys.argv.index("--project-root") + 1]) / "heartbeat.txt"
    subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys,time\nwhile True:\n open(sys.argv[1],'a').write('.'); time.sleep(0.05)",
            str(beat),
        ]
    )
print(json.dumps(hello), flush=True)
if mode == "slow":
    # Concurrent like the real worker: runs.list is slow, everything else instant.
    import threading

    lock = threading.Lock()

    def answer(request):
        if request["op"] == "runs.list":
            time.sleep(1.5)
        with lock:
            print(json.dumps({"id": request["id"], "ok": True, "result": request["op"]}), flush=True)

    for line in sys.stdin:
        threading.Thread(target=answer, args=(json.loads(line),), daemon=True).start()
    sys.exit(0)
for line in sys.stdin:
    request = json.loads(line)
    if mode == "crash":
        print("fatal: simulated crash", file=sys.stderr, flush=True)
        sys.exit(3)
    if mode in {"hang", "grandchild"}:
        time.sleep(60)
    if mode == "huge":
        print(
            json.dumps(
                {"id": request["id"], "ok": True, "result": "x" * (SPEC["max_response_bytes"] + 10)}
            ),
            flush=True,
        )
        continue
    if mode == "wrong_id":
        request["id"] += 100
    print(
        json.dumps({"id": request["id"], "ok": True, "result": {"op": request["op"]}}), flush=True
    )
