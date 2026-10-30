"""Live display preview and saved-run summaries."""

from __future__ import annotations

import json
import math

import pytest

pytest.importorskip("pydantic", minversion="2")

BENCH = dict(
    mode="analytic",
    backend="reference",
    seed=42,
    events=1,
    momentum_gev=2.0,
    bz_tesla=3.8,
    thickness_mm=1.0,
    noise_adc=1.0,
    threshold_adc=5.0,
    response_model="ideal",
    field_model="ideal_bore",
    source_model="transverse_pair",
    muon_pt_min_gev=20.0,
    muon_abs_eta_max=2.4,
    muon_iso_max=0.15,
    mass_min_gev=60.0,
    mass_max_gev=120.0,
)


def test_preview_matches_the_bench_and_is_marked_unsaved():
    import threading

    from heplab.server.workbench import RunConfig, bench, preview

    value = preview({"config": BENCH})
    reference = bench(RunConfig.model_validate(BENCH), threading.Event())
    assert value["preview"] is True and "artifact" not in value
    assert [t["points"] for t in value["tracks"]] == [t["points"] for t in reference["tracks"]]


def test_preview_aims_the_pair_along_eta_and_phi():
    from heplab.server.workbench import preview

    value = preview({"config": BENCH, "eta": 1.0, "phi": -2.0})
    momentum = value["tracks"][0]["truth"]["momentum"]
    pt = math.hypot(momentum["px"], momentum["py"])
    # Track 0 is the negative muon, emitted opposite the aimed direction.
    assert math.asinh(-momentum["pz"] / pt) == pytest.approx(1.0)
    assert math.atan2(-momentum["py"], -momentum["px"]) == pytest.approx(-2.0)
    assert "preview only" in value["source"]


@pytest.mark.parametrize(
    "request_",
    [
        {"config": {**BENCH, "mode": "pythia", "backend": "delphes"}},
        {"config": BENCH, "eta": 1.0},
        {"config": BENCH, "eta": 3.0, "phi": 0.0},
        {"config": BENCH, "unexpected": 1},
    ],
)
def test_preview_rejects_collisions_partial_aim_and_out_of_range(request_):
    from pydantic import ValidationError

    from heplab.server.workbench import preview

    with pytest.raises(ValidationError):
        preview(request_)


def test_preview_route_needs_the_session_token_and_saves_nothing(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    with TestClient(create_app(tmp_path), base_url="http://localhost") as client:
        assert client.post("/api/v1/preview", json={"config": BENCH}).status_code == 403
        headers = {"x-heplab-token": client.get("/api/v1/session").json()["token"]}
        response = client.post("/api/v1/preview", json={"config": BENCH}, headers=headers)
        assert response.status_code == 200 and response.json()["preview"] is True
        bad = client.post("/api/v1/preview", json={"config": BENCH, "eta": 1.0}, headers=headers)
        assert bad.status_code == 422
    assert not list(tmp_path.glob("*.json"))


def test_worker_preview_operation(tmp_path):
    from heplab.desktop import worker

    handlers = worker.operations(tmp_path)
    assert handlers["workbench.preview"](request={"config": BENCH})["preview"] is True
    with pytest.raises(worker.RequestError):
        handlers["workbench.preview"](request={"config": BENCH, "phi": 0.0})


def test_run_summaries_label_saved_runs_newest_first(tmp_path):
    import os

    from heplab.server.workbench import run_summaries

    old, new = tmp_path / "a.json", tmp_path / "b.json"
    old.write_text(json.dumps({"mode": "analytic", "config": BENCH}), encoding="utf-8")
    new.write_text(
        json.dumps(
            {
                "mode": "analytic",
                "config": BENCH,
                "artifact": {"format": "heplab-workbench-result-v2", "created_utc": "2026-10-29"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    os.utime(old, (1, 1))
    rows = run_summaries(tmp_path)
    assert rows[0]["id"] in {"b", "broken"} and rows[-1]["id"] == "a"
    by_id = {row["id"]: row for row in rows}
    assert by_id["b"]["created_utc"] == "2026-10-29" and by_id["b"]["config"] == BENCH
    assert by_id["broken"] == {"id": "broken", "artifact": "broken.json"}
