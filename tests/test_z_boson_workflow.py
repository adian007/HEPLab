"""Contract and replay regressions for the offline guide-to-Workbench handoff."""

import json
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest

from heplab import run
from heplab.labs.z_boson import reopen, reproduce
from heplab.physics import invariant_mass

ROOT = Path(__file__).resolve().parents[1]
PRESET = ROOT / "web/HEPLab.Web/wwwroot/examples/z-boson-preset.json"


def wait_for_job(get, job_id):
    for _ in range(200):
        job = get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.025)
    pytest.fail("the local lab job did not finish")


def test_website_preset_to_desktop_ipc_to_python_replay(tmp_path):
    pytest.importorskip("iminuit")
    from heplab.desktop import worker

    closers = []
    handlers = worker.operations(tmp_path, closers)
    preset = json.loads(PRESET.read_text(encoding="utf-8"))

    def call(op, **args):
        _, name, parameters = worker.validate({"id": 1, "op": op, "args": args}, tmp_path)
        return handlers[name](**parameters)

    try:
        preview = call("workbench.z-boson-preview", preset=preset)
        assert preview["event"] == 1
        assert "Synthetic teaching sample" in preview["scope"]
        with pytest.raises(worker.RequestError):
            call("workbench.z-boson-preview", preset={**preset, "revision": True})
        assert preview["settings"]["event_count"] == 4000
        config = {
            "mode": "z-boson",
            "preset": preset,
            "min_pt_gev": 20,
            "max_rel_iso": 0.15,
            "require_opposite_charge": True,
            "mass_gev": invariant_mass(*preview["muons"]),
            "width_answer": "b",
        }
        job_id = call("jobs.submit", config=config, idempotency_key="practice")["id"]
        assert call("jobs.submit", config=config, idempotency_key="practice")["id"] == job_id
        job = wait_for_job(lambda identity: call("jobs.get", job_id=identity), job_id)
        assert job["status"] == "completed", job
        exported = tmp_path / "download.json"
        exported.write_text(call("workbench.z-boson-download", job_id=job_id)["json"], "utf-8")
        artifact = reopen(exported)
        assert artifact["progress"]["completed"] == 6
        assert artifact["analysis"]["histogram"]["entries"] == 2155
        assert artifact["fit"]["success"]
        assert artifact["fit"]["values"]["mean"] == pytest.approx(91.153, abs=0.005)
        events, result = reproduce(artifact)
        changed = deepcopy(artifact["analysis_config"])
        changed["selection"]["muons"]["max_rel_iso"] = 0.10
        assert run(events, config=changed)["histogram"]["entries"] < result["histogram"]["entries"]
        page = call("workbench.z-boson-report", job_id=job_id)["html"]
        assert "Rediscover the Z boson" in page and "Fitted peak" in page
        exported.write_text(exported.read_text("utf-8").replace("2155", "2154", 1), "utf-8")
        with pytest.raises(ValueError, match="digest mismatch"):
            reopen(exported)
    finally:
        for close in closers:
            close()


def test_loopback_lab_adapters(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    app = create_app(tmp_path)
    preset = json.loads(PRESET.read_text(encoding="utf-8"))
    with TestClient(app, base_url="http://localhost") as client:
        headers = {"X-HEPLab-Token": app.state.jobs.token}
        endpoint = "/api/v1/z-boson/preview"
        assert client.post(endpoint, json=preset).status_code == 403
        assert client.post(endpoint, json=preset, headers=headers).json()["event"] == 1
        rejected = client.post(endpoint, json={**preset, "path": "."}, headers=headers)
        assert rejected.status_code == 422
        assert client.get("/api/v1/z-boson/unknown/download").status_code == 404


def test_cancelled_lab_does_not_publish_a_result(tmp_path, monkeypatch):
    from heplab.labs import z_boson
    from heplab.server.workbench import Jobs, ZBosonRunConfig

    started = threading.Event()
    release = threading.Event()

    def blocked_analysis(**options):
        started.set()
        assert release.wait(5)
        options["progress"](128, 4000)
        pytest.fail("a cancelled job continued computing")

    monkeypatch.setattr(z_boson, "analyze", blocked_analysis)
    jobs = Jobs(tmp_path)
    try:
        identity = jobs.submit(
            ZBosonRunConfig(
                mode="z-boson",
                preset=json.loads(PRESET.read_text("utf-8")),
                min_pt_gev=20,
                max_rel_iso=0.15,
                require_opposite_charge=True,
            )
        )
        assert started.wait(5)
        jobs.cancel(identity)
        release.set()
        assert wait_for_job(jobs.get, identity)["status"] == "cancelled"
        assert not (tmp_path / f"{identity}.json").exists()
    finally:
        release.set()
        jobs.close()
