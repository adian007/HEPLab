"""Independent limits, statistical checks and real local API lifecycle regressions."""

import json
import math
import threading
import time

import pytest

from heplab.physics.engine import execute

ADDRESS = {
    "master_seed": 42,
    "event_key": "material-test",
    "object_id": 0,
    "stage_id": "test",
    "counter": 0,
    "correlation_group": "nominal",
    "model_id": "test",
}
STATE = {
    "position": [0, 0, 0],
    "momentum": {"energy": math.sqrt(101), "px": 10, "py": 0, "pz": 0},
    "charge": 1,
    "time_ns": 0,
}
SLAB = {
    "id": "test-slab",
    "thickness_m": 0.001,
    "radiation_length_m": 0.1,
    "stopping_power_gev_per_m": 0.4,
    "min_beta_gamma": 1.0,
    "max_beta_gamma": 100.0,
    "scatter": True,
}
ELECTRONICS = {
    "gain_adc_per_gev": 1000.0,
    "pedestal_adc": 0.0,
    "noise_sigma_adc": 0.0,
    "threshold_adc": 5.0,
    "saturation_adc": 255.0,
}


def test_material_analytic_loss_mass_zero_limit_and_invalid_domain():
    result = execute({"op": "material", "state": STATE, "slab": SLAB, "address": ADDRESS})
    assert result["deposit_gev"] == pytest.approx(0.0004)
    p = result["state"]["momentum"]
    assert p["energy"] ** 2 - sum(p[k] ** 2 for k in ("px", "py", "pz")) == pytest.approx(1)
    assert abs(result["energy_residual_gev"]) < 1e-14
    zero = execute(
        {"op": "material", "state": STATE, "slab": {**SLAB, "thickness_m": 0}, "address": ADDRESS}
    )
    assert zero["state"]["position"] == pytest.approx([0, 0, 0])
    assert zero["state"]["momentum"] == pytest.approx(STATE["momentum"])
    for update in (
        {"thickness_m": 1},
        {"radiation_length_m": 0},
        {"max_beta_gamma": 2},
        {"thickness_m": 1e-9},
        {"scatter": 1},
    ):
        with pytest.raises(ValueError):
            execute(
                {"op": "material", "state": STATE, "slab": {**SLAB, **update}, "address": ADDRESS}
            )


def test_highland_projected_width_and_channel_noise_statistics():
    angles, signals = [], []
    for i in range(2000):
        address = {**ADDRESS, "object_id": i}
        value = execute({"op": "material", "state": STATE, "slab": SLAB, "address": address})
        p = value["state"]["momentum"]
        angles.append(p["py"] / p["px"])
        digit = execute(
            {
                "op": "digitize",
                "deposit_gev": 0.1,
                "config": {**ELECTRONICS, "noise_sigma_adc": 3},
                "address": address,
            }
        )
        signals.append(digit["analog_adc"])
    mean = sum(angles) / len(angles)
    width = math.sqrt(sum((x - mean) ** 2 for x in angles) / (len(angles) - 1))
    theta = 0.0136 / (100 / math.sqrt(101)) * math.sqrt(0.01) * (1 + 0.038 * math.log(0.01))
    assert abs(mean) < theta * 0.08
    assert width == pytest.approx(theta, rel=0.06)
    average = sum(signals) / len(signals)
    sigma = math.sqrt(sum((x - average) ** 2 for x in signals) / (len(signals) - 1))
    assert average == pytest.approx(100, abs=0.25)
    assert sigma == pytest.approx(3, rel=0.06)


def test_digits_do_not_create_or_modify_transport_energy():
    for deposit, expected in ((0.001, None), (0.005, 5), (0.1, 100), (1, 255)):
        value = execute(
            {"op": "digitize", "deposit_gev": deposit, "config": ELECTRONICS, "address": ADDRESS}
        )
        assert value["adc"] == expected
        assert value["deposit_gev"] == deposit
        assert value["saturated"] == (deposit > 0.255)


def test_local_gui_job_lifecycle_token_origin_bounds_and_export(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        root = client.get("/")
        assert root.status_code == 200
        workbench = client.get("/workbench")
        assert workbench.status_code == 200
        assert "HEPLab Workbench" in workbench.text
        assert client.get("/ui/workbench.js").status_code == 200
        assert client.get("/ui/workbench.js").headers["cache-control"] == "no-store"
        assert client.get("/ui/../app.py").status_code == 404
        assert client.post("/api/v1/jobs", json={}).status_code == 403
        headers = {"x-heplab-token": client.get("/api/v1/session").json()["token"]}
        assert (
            client.post(
                "/api/v1/jobs", json={}, headers={**headers, "origin": "https://bad.example"}
            ).status_code
            == 403
        )
        assert client.post("/api/v1/jobs", json={"seed": 0}, headers=headers).status_code == 422
        assert (
            client.post("/api/v1/jobs", json={"executable": "whoami"}, headers=headers).status_code
            == 422
        )
        response = client.post("/api/v1/jobs", json={}, headers=headers)
        assert response.status_code == 202
        identity = response.json()["id"]
        for _ in range(100):
            job = client.get(f"/api/v1/jobs/{identity}").json()
            if job["status"] in {"failed", "completed"}:
                break
            time.sleep(0.01)
        assert job["status"] == "completed", job
        value = json.loads((tmp_path / f"{identity}.json").read_text())
        assert value["events"] == 1
        assert len(value["tracks"]) == 2
        assert value["validation"] == "educational_unvalidated"
        assert client.get(f"/api/v1/jobs/{identity}/events/0").status_code == 200
        assert client.get(f"/api/v1/jobs/{identity}/events/1").status_code == 404
        assert client.post("/api/v1/jobs", content=b"x" * 16385, headers=headers).status_code == 413
        keyed = {**headers, "Idempotency-Key": "repeat-command-1"}
        first = client.post("/api/v1/jobs", json={}, headers=keyed).json()
        second = client.post("/api/v1/jobs", json={}, headers=keyed).json()
        assert first["id"] == second["id"]
        assert client.post("/api/v1/jobs", json={"seed": 43}, headers=keyed).status_code == 409


def test_workbench_cancellation_before_transport():
    pytest.importorskip("pydantic")
    from heplab.server.workbench import RunConfig, bench

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        bench(RunConfig(), cancel)


def test_backend_incompatibility_never_silently_falls_back():
    pytest.importorskip("pydantic")
    from heplab.server.workbench import RunConfig

    for mode, backend in (("pythia", "rust"), ("pythia", "reference"), ("analytic", "delphes")):
        with pytest.raises(ValueError, match="requires"):
            RunConfig(mode=mode, backend=backend)
    assert RunConfig(mode="pythia", backend="delphes").backend == "delphes"


def test_native_commit_wins_over_late_cancellation(tmp_path, monkeypatch):
    pytest.importorskip("pydantic")
    from heplab.server.workbench import Jobs, RunConfig

    def committed_run(*, output, cancel, **_kwargs):
        output.mkdir()
        (output / "run.json").write_text(json.dumps({"summary": {"events": 1}}))
        (output / "preview.json").write_text(json.dumps({"muons": [], "event": 0}))
        cancel.set()  # cancellation arrives after native publication has committed
        return output

    monkeypatch.setattr("heplab.sim.pipeline.run_chain", committed_run)
    monkeypatch.setattr(
        "heplab.readers.delphes.read",
        lambda *_args, **_kwargs: iter(
            [{"EventInfo": {"weight": 1.0}, "Muon": [], "Jet": [], "MET": {"pt": None}}]
        ),
    )
    jobs = Jobs(tmp_path)
    try:
        identity = jobs.submit(RunConfig(mode="pythia", backend="delphes"))
        for _ in range(100):
            value = jobs.get(identity)
            if value["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.01)
        assert value["status"] == "completed", value
        assert (tmp_path / f"{identity}.json").is_file()
    finally:
        jobs.close()
