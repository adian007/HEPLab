"""Regressions for the 2026-10-29 QA audit fixes (worker, jobs, uploads, data kind)."""

import io
import json
import math
import time

import pytest

from heplab.desktop import worker
from heplab.physics.reference import WeightedHistogram


def test_worker_survives_unexpected_exception_types(tmp_path, monkeypatch):
    def broken(root, closers=None):
        handlers = original(root, closers)
        handlers["runs.list"] = lambda: (_ for _ in ()).throw(ZeroDivisionError("boom"))
        return handlers

    original = worker.operations
    monkeypatch.setattr(worker, "operations", broken)
    stdin = io.StringIO(
        json.dumps({"id": 1, "op": "runs.list", "args": {}})
        + "\n"
        + json.dumps({"id": 2, "op": "engine.capabilities", "args": {}})
        + "\n"
    )
    stdout = io.StringIO()
    assert worker.serve(tmp_path, stdin, stdout) == 0
    # Requests run concurrently, so replies are matched by id, not position.
    replies = {reply.get("id"): reply for reply in map(json.loads, stdout.getvalue().splitlines())}
    assert replies[1]["ok"] is False and replies[1]["error"]["code"] == "operation_failed"
    assert "ZeroDivisionError" in replies[1]["error"]["message"]
    assert replies[2]["id"] == 2 and replies[2]["ok"] is True


def test_worker_replaces_non_finite_numbers_with_null():
    stream = io.StringIO()
    worker.respond(
        stream, {"id": 1, "ok": True, "result": {"ratio": math.nan, "v": [1.0, -math.inf]}}
    )
    assert json.loads(stream.getvalue()) == {
        "id": 1,
        "ok": True,
        "result": {"ratio": None, "v": [1.0, None]},
    }


def test_finished_jobs_are_evicted_instead_of_exhausting_the_session(tmp_path):
    pytest.importorskip("pydantic")
    from heplab.server.workbench import Jobs, RunConfig

    jobs = Jobs(tmp_path)
    try:
        for seed in range(80):
            identity = jobs.submit(RunConfig(seed=seed + 1))
            for _ in range(500):
                if jobs.get(identity)["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.01)
            assert jobs.get(identity)["status"] == "completed"
        # Finished runs hold no memory: results are read back from their artifacts.
        assert not jobs.live and not jobs.cancels
        first = next(path.stem for path in tmp_path.glob("*.json"))
        assert jobs.get(first)["status"] == "completed"
        jobs.cancel(first)  # cancelling a finished, evicted job is a no-op
        with pytest.raises(KeyError):
            jobs.cancel("f" * 24)
    finally:
        jobs.close()


def test_corrupt_persisted_job_is_unknown_not_a_crash(tmp_path):
    pytest.importorskip("pydantic")
    from heplab.server.workbench import Jobs

    jobs = Jobs(tmp_path)
    try:
        (tmp_path / ("a" * 24 + ".json")).write_text("[1, 2]")
        (tmp_path / ("b" * 24 + ".json")).write_text("{not json")
        for identity in ("a" * 24, "b" * 24):
            with pytest.raises(KeyError):
                jobs.get(identity)
    finally:
        jobs.close()


def test_stale_upload_no_longer_blocks_imports(tmp_path, monkeypatch):
    pytest.importorskip("pydantic")
    from heplab.server import data_workspace
    from heplab.server.data_workspace import DataWorkspace

    workspace = DataWorkspace(tmp_path)
    abandoned = workspace.import_begin(dict(name="a.root", kind="data", size=4))["id"]
    with pytest.raises(ValueError, match="active import"):
        workspace.import_begin(dict(name="b.root", kind="data", size=4))
    with pytest.raises(ValueError, match="upload id"):
        workspace.import_chunk(dict(id=["x"], offset=0, base64="cm9vdA=="))
    monkeypatch.setattr(data_workspace, "UPLOAD_IDLE_S", 0.0)
    fresh = workspace.import_begin(dict(name="b.root", kind="data", size=4))["id"]
    assert fresh != abandoned and abandoned not in workspace.uploads
    assert not (workspace.root / "imports" / (abandoned + ".part")).exists()


def test_histogram_fill_is_transactional_per_bin():
    hist = WeightedHistogram([0.0, 1.0, 2.0])
    hist.fill(0.5, 2.0)
    before = hist.snapshot()
    with pytest.raises(ValueError):
        hist.fill(0.5, math.inf)
    assert hist.snapshot() == before
    hist.fill(1.5)
    assert hist.snapshot()["sumw_with_flow"][1:3] == [2.0, 1.0]


def test_empty_dimuon_run_is_not_labelled_mixed():
    from heplab.analyses.dimuon.run import process

    assert process([], {})["data_kind"] == "none"


def test_cli_declares_kind_for_unflagged_json_events(tmp_path):
    from heplab.cli import main

    event = {
        "EventInfo": {"run": 1, "luminosity_block": 1, "event": 1, "weight": 1.0},
        "Muon": [],
    }
    source = tmp_path / "events.json"
    source.write_text(json.dumps([event]))
    output = tmp_path / "out.json"
    assert main(["run", "dimuon", "--input", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["data_kind"] == "data"
