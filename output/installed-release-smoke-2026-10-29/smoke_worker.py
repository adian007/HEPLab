"""Exercise the rebuilt frozen worker independently of source and launcher overrides."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE / "Packaged Smoke Project"
ROOT.mkdir(exist_ok=True)
BINARY = Path(os.environ["LOCALAPPDATA"]) / "HEPLab/heplab-worker.exe"
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "HEPLAB_"))}


class Worker:
    def __init__(self):
        self.responses = queue.Queue()
        self.identity = 0
        self.log = (HERE / "worker-stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(BINARY), "--project-root", str(ROOT)], cwd=HERE,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding="utf-8", env=ENV,
        )
        def read():
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
            self.responses.put({"error": "worker closed stdout"})
        threading.Thread(target=read, daemon=True).start()
        self.hello = self.responses.get(timeout=40)
        assert self.hello["protocol"] == "heplab-desktop-ipc-v1", self.hello

    def call(self, operation, **args):
        self.identity += 1
        self.process.stdin.write(json.dumps({"id": self.identity, "op": operation, "args": args}) + "\n")
        self.process.stdin.flush()
        result = self.responses.get(timeout=130)
        assert result.get("id") == self.identity and result.get("ok"), result
        return result["result"]

    def wait(self, identity, seconds=180):
        deadline = time.monotonic() + seconds
        while True:
            job = self.call("jobs.get", job_id=identity)
            if job["status"] not in {"queued", "running"}:
                return job
            assert time.monotonic() < deadline, job
            time.sleep(.2)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], check=False)
            raise
        finally:
            self.log.close()
        assert self.process.returncode == 0


report = {"status": "running", "worker": str(BINARY), "project": str(ROOT)}
w = Worker()
try:
    report["engine"] = w.call("engine.capabilities")
    assert report["engine"]["rust_extension"]
    assert len(w.call("project.overview")["capabilities"]) == 4
    before = sorted((ROOT / "artifacts").glob("*.json"))
    preview = w.call("workbench.preview", request={"config": {"backend": "rust", "momentum_gev": 5.0}, "eta": .5, "phi": 1.0})
    assert preview["preview"] and len(preview["tracks"]) == 2
    assert sorted((ROOT / "artifacts").glob("*.json")) == before
    report["preview_unsaved"] = True
    job = w.call("jobs.submit", config={"backend": "rust", "source_model": "angular_sample", "events": 4, "seed": 42})
    saved = w.wait(job["id"])
    assert saved["status"] == "completed", saved
    event = w.call("jobs.event", job_id=job["id"], index=3)
    assert event["event"] == 3 and event["events"] == 4
    report["rust_run"] = {"id": job["id"], "events": 4, "event_navigation": True}
    library = w.call("data.library")
    assert {item["id"] for item in library} >= {"cms-run2016g", "cms-dy-ul16"}
    cms = w.call("data.analyze", config={})
    count = cms["populations"]["data"]["selected_events"]
    assert count > 0
    for index in [0, count - 1]:
        recorded = w.call("data.event", analysis_id=cms["id"], index=index)
        assert recorded["event"] == index and recorded["objects"] is not None
        assert recorded["objects"]["source"]["sha256"]
        assert recorded["objects"]["vertex"]["position_m"]
    report["cms"] = {"analysis_id": cms["id"], "data_selected": count,
        "mc_selected": cms["populations"]["mc"]["selected_events"], "first_last_navigation": True,
        "sidecars_joined": True, "certification_sha256": cms["certification_sha256"]}
    print("PASS: Rust sample, unsaved preview, CMS analysis and first/last sidecar joins", flush=True)
    session = w.call("workbench.session")
    report["simulation"] = session["simulation"]
    if session["simulation"]["available"]:
        collision = w.call("jobs.submit", config={"mode": "pythia", "backend": "delphes", "events": 20, "seed": 42})
        collision_job = w.wait(collision["id"])
        assert collision_job["status"] == "completed", collision_job
        generated = collision_job["result"]
        assert generated["summary"]["events"] == 20
        selected = next(row["event"] for row in generated["analysis"]["event_rows"] if row["selected"])
        assert w.call("jobs.event", job_id=collision["id"], index=selected)["event_info"]["selected"]
        report["collisions"] = {"id": collision["id"], "events": 20, "selected": generated["analysis"]["selected_events"], "selected_event_navigation": True}
        started = time.time()
        cancelled = w.call("jobs.submit", config={"mode": "pythia", "backend": "delphes", "events": 1000, "seed": 43})
        deadline = time.monotonic() + 60
        while not any(p.stat().st_mtime >= started for p in (ROOT / "artifacts").glob(".sim-*/events.root")):
            state = w.call("jobs.get", job_id=cancelled["id"])
            assert state["status"] in {"queued", "running"}, state
            assert time.monotonic() < deadline
            time.sleep(.1)
        w.call("jobs.cancel", job_id=cancelled["id"])
        assert w.wait(cancelled["id"])["status"] == "cancelled"
        assert not (ROOT / "artifacts" / (cancelled["id"] + ".json")).exists()
        report["active_generation_cancelled"] = True
        print("PASS: collision generation, selection, navigation and active cancellation", flush=True)
finally:
    w.close()
w = Worker()
try:
    assert w.call("jobs.event", job_id=job["id"], index=3) == event
    assert w.call("data.get", analysis_id=cms["id"]) == cms
    report["restart_reopened"] = True
finally:
    w.close()
report["status"] = "passed"
(HERE / "worker-acceptance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
