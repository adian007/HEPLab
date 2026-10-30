"""Scientific and persistence contracts for navigable synthetic muon samples."""

import math
import threading
import time

import pytest

pytest.importorskip("pydantic", minversion="2")

from heplab.physics.reference import FourVector  # noqa: E402
from heplab.server.workbench import Jobs, RunConfig, analyze_events, bench  # noqa: E402


def wait(jobs, identity):
    deadline = time.monotonic() + 30
    while (job := jobs.get(identity))["status"] in {"queued", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert job["status"] == "completed", job
    return job


def test_seeded_angular_events_have_varied_directions_and_correct_pair_kinematics():
    config = RunConfig(source_model="angular_sample", events=3)
    events = [bench(config, threading.Event(), i) for i in range(3)]
    assert events[2] == bench(config, threading.Event(), 2)
    assert events[0]["tracks"][0]["truth"] != events[1]["tracks"][0]["truth"]
    for event in events:
        expected_models = {item["id"] for item in event["model_spec"]["components"]}
        assert set(event["tracks"][0]["model_ids"]) == expected_models
        first, second = [FourVector(**t["truth"]["momentum"]) for t in event["tracks"]]
        assert first.momentum == pytest.approx(45)
        assert (first.px + second.px, first.py + second.py, first.pz + second.pz) == (0, 0, 0)
        assert (first + second).physical_mass == pytest.approx(2 * math.hypot(45, 0.10565839))
        pt = math.hypot(first.px, first.py)
        assert 0 < pt <= first.momentum
        assert abs(math.asinh(first.pz / pt)) < 2.4
    changed = bench(config.model_copy(update={"seed": 43}), threading.Event())
    assert changed["tracks"][0]["truth"] != events[0]["tracks"][0]["truth"]


def test_sample_events_and_observables_survive_a_worker_restart(tmp_path):
    config = RunConfig(source_model="angular_sample", events=4, response_model="delphes_reference")
    jobs = Jobs(tmp_path)
    try:
        identity = jobs.submit(config)
        result = wait(jobs, identity)["result"]
        assert result["events"] == 4
        assert len(result["analysis"]["samples"]) == 8
        assert len(result["analysis"]["pairs"]) == 4
        assert result["artifact"]["run_id"] == identity
        assert result["artifact"]["schema"] == "heplab-run-artifact-v1"
        assert result["artifact"]["scope"] == "full_run"
        assert len(result["artifact"]["result_sha256"]) == 64
        assert all(s["pt_gev"] != 45 for s in result["analysis"]["samples"])
        third = jobs.event(identity, 2)
        assert third["event"] == 2 and third["events"] == 4
        assert third["tracks"] != result["tracks"]
        assert third["analysis"] == result["analysis"]
        assert third["artifact"]["schema"] == "heplab-event-view-v1"
        assert third["artifact"]["scope"] == "selected_event_view"
        assert third["artifact"]["parent_run_sha256"] == result["artifact"]["result_sha256"]
        assert third["artifact"]["event_index"] == 2
    finally:
        jobs.close()
    restarted = Jobs(tmp_path)
    try:
        assert restarted.get(identity)["result"] == result
        assert restarted.event(identity, 2) == third
        with pytest.raises(ValueError):
            restarted.event(identity, 4)
        with pytest.raises(KeyError):
            restarted.get("../outside")
    finally:
        restarted.close()


def test_response_observables_include_sampled_kinematics_and_track_losses():
    config = RunConfig(source_model="angular_sample", response_model="delphes_reference")
    events = [bench(config, threading.Event(), i) for i in range(8)]
    analysis = analyze_events(events)
    samples = analysis["samples"]
    assert len(samples) == 16
    for event, pair in zip(events, analysis["pairs"], strict=True):
        accepted = [t["reference_response"]["sample"]["objects"] for t in event["tracks"]]
        assert (pair["response_mass_gev"] is not None) == all(accepted)
    matched = [s for s in samples if s["response_status"] == "accepted"]
    assert matched
    assert any(abs(s["response_pt_gev"] - s["pt_gev"]) > 0.001 for s in matched)
    assert all((s["response_pt_gev"] is None) == (s["response_status"] == "lost") for s in samples)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_model": "angular_sample", "events": 201},
        {
            "source_model": "angular_sample",
            "momentum_gev": 20.0,
            "response_model": "delphes_reference",
        },
    ],
)
def test_sample_workload_and_response_domains_are_checked(kwargs):
    with pytest.raises(ValueError):
        RunConfig(**kwargs)


def test_cancel_during_sample_does_not_publish_partial_results(tmp_path, monkeypatch):
    import heplab.server.workbench as workbench

    started = threading.Event()
    original = workbench.bench

    def held(config, cancel, event=0):
        started.set()
        assert cancel.wait(timeout=5)
        return original(config, cancel, event)

    monkeypatch.setattr(workbench, "bench", held)
    jobs = Jobs(tmp_path)
    try:
        identity = jobs.submit(RunConfig(source_model="angular_sample", events=3))
        assert started.wait(timeout=5)
        jobs.cancel(identity)
        deadline = time.monotonic() + 5
        while jobs.get(identity)["status"] in {"queued", "running"}:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert jobs.get(identity)["status"] == "cancelled"
        assert not (tmp_path / f"{identity}.json").exists()
        assert not (tmp_path / f"{identity}-events").exists()
        assert not list(tmp_path.glob(".bench-*"))
    finally:
        jobs.close()


def test_native_rust_matches_reference_for_angular_tracks_and_response():
    pytest.importorskip("heplab_kernels")
    config = RunConfig(source_model="angular_sample", response_model="delphes_reference")
    reference = bench(config, threading.Event(), 5)
    native = bench(config.model_copy(update={"backend": "rust"}), threading.Event(), 5)
    for left, right in zip(reference["tracks"], native["tracks"], strict=True):
        assert left["truth"] == right["truth"]
        assert left["material"]["deposit_gev"] == pytest.approx(
            right["material"]["deposit_gev"], abs=1e-12
        )
        assert left["digit"]["adc"] == right["digit"]["adc"]
        for key in ["energy", "px", "py", "pz"]:
            assert left["material"]["state"]["momentum"][key] == pytest.approx(
                right["material"]["state"]["momentum"][key], rel=1e-10, abs=1e-10
            )
