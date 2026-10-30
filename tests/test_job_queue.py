"""Durable job queue: FIFO execution, reattachment and recovery after a worker dies."""

import json
import threading
import time

import pytest

pytest.importorskip("pydantic")

from heplab.server import workbench  # noqa: E402
from heplab.server.jobstore import JobStore, OwnerLock  # noqa: E402
from heplab.server.workbench import Jobs, RunConfig  # noqa: E402


def wait(jobs, identity, timeout=30):
    deadline = time.monotonic() + timeout
    while (job := jobs.get(identity))["status"] in {"queued", "running"}:
        assert time.monotonic() < deadline, job
        time.sleep(0.01)
    return job


def orphan(root, status, *, attempts=0, config=None):
    """Write a record as if a now-dead process had left it behind."""
    store = JobStore(root, "deadbeef00000000")
    identity = "c" * 23 + str(attempts)
    body = (config or RunConfig(seed=5)).model_dump()
    store.insert(identity, body, "f" * 64, None)
    store.update(identity, status=status, attempts=attempts)
    store.close()  # releasing the owner lock is what a process exit does
    return identity


@pytest.fixture
def held(monkeypatch):
    """Block runs inside bench() until released, to observe queued/running states."""
    gate, started = threading.Event(), threading.Event()
    original = workbench.bench

    def bench(config, cancel, event=0):
        started.set()
        while not gate.wait(0.01):
            if cancel.is_set():
                raise RuntimeError("run cancelled")
        return original(config, cancel, event)

    monkeypatch.setattr(workbench, "bench", bench)
    return gate, started


def test_runs_queue_in_order_instead_of_being_rejected(tmp_path, held):
    gate, started = held
    jobs = Jobs(tmp_path)
    try:
        first = jobs.submit(RunConfig(seed=1))
        assert started.wait(5)
        second = jobs.submit(RunConfig(seed=2))
        assert jobs.get(first)["status"] == "running"
        assert jobs.get(second)["status"] == "queued"
        assert [job["id"] for job in jobs.list()][:2] == [second, first]
        assert "result" not in jobs.list()[0]
        gate.set()
        assert wait(jobs, first)["status"] == "completed"
        assert wait(jobs, second)["status"] == "completed"
    finally:
        gate.set()
        jobs.close()


def test_cancelling_a_queued_run_never_starts_it(tmp_path, held):
    gate, started = held
    jobs = Jobs(tmp_path)
    try:
        first = jobs.submit(RunConfig(seed=1))
        assert started.wait(5)
        second = jobs.submit(RunConfig(seed=2))
        jobs.cancel(second)
        assert jobs.get(second)["status"] == "cancelled"
        gate.set()
        assert wait(jobs, first)["status"] == "completed"
        assert jobs.get(second)["status"] == "cancelled"
        assert not (tmp_path / f"{second}.json").exists()
    finally:
        gate.set()
        jobs.close()


def test_idempotency_keys_survive_a_restart(tmp_path):
    jobs = Jobs(tmp_path)
    try:
        identity = jobs.submit(RunConfig(seed=3), "key-1")
        wait(jobs, identity)
    finally:
        jobs.close()
    restarted = Jobs(tmp_path)
    try:
        assert restarted.submit(RunConfig(seed=3), "key-1") == identity
        with pytest.raises(ValueError, match="different parameters"):
            restarted.submit(RunConfig(seed=4), "key-1")
    finally:
        restarted.close()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_runs_left_by_a_dead_worker_are_reclaimed_and_finish(tmp_path, status):
    identity = orphan(tmp_path, status)
    jobs = Jobs(tmp_path)
    try:
        job = wait(jobs, identity)
        assert job["status"] == "completed", job
        assert job["result"]["artifact"]["run_id"] == identity
        assert job.get("attempt") == (2 if status == "running" else None)
    finally:
        jobs.close()


def test_a_run_interrupted_twice_fails_instead_of_looping(tmp_path):
    identity = orphan(tmp_path, "running", attempts=1)
    jobs = Jobs(tmp_path)
    try:
        job = jobs.get(identity)
        assert job["status"] == "failed" and "worker restarts" in job["error"]
    finally:
        jobs.close()


def test_a_live_engines_runs_are_not_stolen(tmp_path, held):
    gate, started = held
    owner = Jobs(tmp_path)
    try:
        identity = owner.submit(RunConfig(seed=1))
        assert started.wait(5)
        other = Jobs(tmp_path)
        try:
            assert other.get(identity)["status"] == "running"
            with pytest.raises(ValueError, match="another HEPLab process"):
                other.cancel(identity)
        finally:
            other.close()
        gate.set()
        assert wait(owner, identity)["status"] == "completed"
    finally:
        gate.set()
        owner.close()


def test_shutdown_leaves_unfinished_runs_for_the_next_start(tmp_path, held):
    gate, started = held
    jobs = Jobs(tmp_path)
    identity = jobs.submit(RunConfig(seed=1))
    assert started.wait(5)
    jobs.close()  # app exit: cancels the in-flight run without blaming the user
    gate.set()
    restarted = Jobs(tmp_path)
    try:
        job = wait(restarted, identity)
        assert job["status"] == "completed", job
        assert "attempt" not in job  # a clean shutdown costs no retry attempt
    finally:
        restarted.close()


def test_unreadable_stored_config_fails_cleanly(tmp_path):
    identity = orphan(tmp_path, "queued")
    store = JobStore(tmp_path, "0123456789abcdef")
    with store.db:
        store.db.execute(
            "UPDATE jobs SET config = ? WHERE id = ?", (json.dumps({"mode": "?"}), identity)
        )
    store.close()
    jobs = Jobs(tmp_path)
    try:
        assert jobs.get(identity)["status"] == "failed"
    finally:
        jobs.close()


def test_owner_lock_is_exclusive_until_released(tmp_path):
    first, second = OwnerLock(tmp_path / "a.lock"), OwnerLock(tmp_path / "a.lock")
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release(remove=True)
    assert not (tmp_path / "a.lock").exists()


def test_terminal_retention_evicts_database_rows_and_owned_artifacts(tmp_path):
    identity = orphan(tmp_path, "completed")
    for path in (
        tmp_path / f"{identity}.json",
        tmp_path / f"{identity}-events" / "0.json",
        tmp_path / f"{identity}-simulation" / "run.json",
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    store = JobStore(tmp_path, "0123456789abcdef")
    with store.db:
        store.db.execute(
            "UPDATE jobs SET created = ? WHERE id = ?", (time.time() - 31 * 86400, identity)
        )
    store.close()

    jobs = Jobs(tmp_path)
    try:
        assert jobs.store.get(identity) is None
        assert not (tmp_path / f"{identity}.json").exists()
        assert not (tmp_path / f"{identity}-events").exists()
        assert not (tmp_path / f"{identity}-simulation").exists()
    finally:
        jobs.close()
