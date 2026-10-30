"""Desktop worker IPC contract (DESKTOP-002/003): bounded, allowlisted, path-confined."""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from desktop.build_worker import validate_library

from heplab.desktop import worker
from heplab.lab import daq

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts/examples/lab-device-profile.json"


def exchange(root: Path, *lines: str) -> list[dict]:
    output = io.StringIO()
    assert worker.serve(root, io.StringIO("".join(line + "\n" for line in lines)), output) == 0
    return [json.loads(line) for line in output.getvalue().splitlines()]


def request(identity: int, op: str, **args) -> str:
    return json.dumps({"id": identity, "op": op, "args": args})


def test_handshake_names_protocol_version_and_exact_operations(tmp_path):
    hello = exchange(tmp_path)[0]
    assert hello["protocol"] == "heplab-desktop-ipc-v1"
    assert hello["worker_version"] == worker.__version__
    assert hello["operations"] == sorted(worker.SPEC["operations"])
    assert set(worker.operations(tmp_path)) == set(worker.SPEC["operations"])


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("not json", "malformed"),
        (json.dumps({"id": 1, "op": "runs.list"}), "malformed"),
        (json.dumps({"id": 1, "op": "runs.list", "args": {}, "extra": 1}), "malformed"),
        (request(1, "os.system", command="rm -rf /"), "unknown_operation"),
        (request(1, "runs.list", shell="true"), "invalid_arguments"),
        (request(1, "runs.get", run_id="../secret"), "invalid_arguments"),
        (request(1, "lab.profile", profile="../outside.json"), "path_rejected"),
        (request(1, "lab.profile", profile="/etc/passwd"), "path_rejected"),
        (request(1, "lab.profile", profile="C:/Windows/win.ini"), "path_rejected"),
        (request(1, "lab.profile", profile="a\\..\\b"), "path_rejected"),
        (request(1, "lab.profile", profile="missing.json"), "not_found"),
        (request(1, "lab.profile", profile="x" * 2000), "invalid_arguments"),
        ("OVERSIZED", "too_large"),
    ],
)
def test_rejections_keep_the_stream_framed(tmp_path, line, code):
    if line == "OVERSIZED":
        line = json.dumps({"id": 1, "op": "x", "args": {}, "pad": "y" * 70000})
    replies = exchange(tmp_path, line, request(7, "runs.list"))
    assert replies[1]["ok"] is False and replies[1]["error"]["code"] == code
    assert replies[2] == {"id": 7, "ok": True, "result": []}


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        (tmp_path / "link.json").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")
    reply = exchange(tmp_path, request(1, "lab.profile", profile="link.json"))[1]
    assert reply["error"]["code"] == "path_rejected"


def test_lab_replay_through_ipc_writes_inside_project_only(tmp_path):
    shutil.copy(EXAMPLE, tmp_path / "profile.json")
    daq.write_fixture(tmp_path / "run.bin", [("hit", 0, 10, 0), ("trigger", 0, 11, 1)])
    replay = request(
        3,
        "lab.replay",
        profile="profile.json",
        raw="run.bin",
        output="out/run.json",
        trigger_source="1",
    )
    # Requests run concurrently: the duplicate is refused while (or after) the
    # first writes, and replies may arrive in either order.
    done, refused = sorted(exchange(tmp_path, replay, replay)[1:], key=lambda r: not r["ok"])
    assert done["ok"], done
    assert done["result"]["output"] == "out/run.json"
    assert done["result"]["record"]["stages"]["efficiency"]["numerator"] == 1
    assert refused["error"]["code"] == "exists"


def test_simulator_job_lifecycle_through_worker(tmp_path):
    pytest.importorskip("pydantic")
    import time

    closers: list = []
    handlers = worker.operations(tmp_path, closers)

    def call(op, **args):
        _, name, checked = worker.validate({"id": 1, "op": op, "args": args}, tmp_path)
        return handlers[name](**checked)

    session = call("workbench.session")
    assert session["token"] == "desktop-ipc" and "engine" in session
    assert call("detector.display")["layers"]
    config = {"mode": "analytic", "backend": "reference", "seed": 7, "events": 1}
    job = call("jobs.submit", config=config, idempotency_key="key-1")
    assert call("jobs.submit", config=config, idempotency_key="key-1")["id"] == job["id"]
    deadline = time.monotonic() + 60
    while (state := call("jobs.get", job_id=job["id"]))["status"] in {"queued", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert state["status"] == "completed", state
    event = call("jobs.event", job_id=job["id"], index=0)
    assert event["tracks"] and event["mode"] == "analytic"
    assert (tmp_path / "artifacts" / f"{job['id']}.json").is_file()
    with pytest.raises(worker.RequestError, match="unknown event") as error:
        call("jobs.event", job_id=job["id"], index=1)
    with pytest.raises(worker.RequestError) as error:
        call("jobs.get", job_id="0" * 24)
    assert error.value.code == "not_found"
    with pytest.raises(worker.RequestError) as error:
        call("jobs.submit", config={"mode": "analytic", "executable": "cmd.exe"})
    assert error.value.code == "invalid_arguments"
    with pytest.raises(worker.RequestError) as error:
        call("jobs.event", job_id=job["id"], index=True)
    assert error.value.code == "invalid_arguments"
    for close in closers:
        close()


def test_desktop_project_payloads_match_the_web_routes(tmp_path):
    replies = exchange(tmp_path, request(1, "project.overview"), request(2, "project.evidence"))
    assert replies[1]["ok"] and replies[2]["ok"]
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    app = create_app(tmp_path / "artifacts")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/v1/project/overview").json() == replies[1]["result"]
        assert client.get("/api/v1/project/evidence").json() == replies[2]["result"]


def test_workbench_bundles_offline_guided_tour():
    static = ROOT / "src/heplab/server/static"
    assert (static / "vendor/introjs/intro.min.js").is_file()
    assert (static / "vendor/introjs/introjs.min.css").is_file()
    assert (static / "vendor/introjs/LICENSE.txt").is_file()
    source = (static / "workbench.js").read_text(encoding="utf-8")
    assert "startGuidedTour" in source
    assert "window.introJs.tour()" in source


def test_shell_configuration_matches_worker_and_stays_locked_down():
    desktop = ROOT / "desktop/src-tauri"
    main_rs = (desktop / "src/main.rs").read_text(encoding="utf-8")
    assert f'EXPECTED_WORKER_VERSION: &str = "{worker.__version__}"' in main_rs
    conf = json.loads((desktop / "tauri.conf.json").read_text(encoding="utf-8"))
    assert conf["version"].replace("-dev.", ".dev") == worker.__version__
    # One-dir worker shipped as a resource (no one-file temp unpacking).
    assert "externalBin" not in conf["bundle"]
    assert conf["bundle"]["resources"] == {"worker/": "worker/"}
    assert '.join("worker")' in main_rs and "resource_dir()" in main_rs
    assert '"--onedir"' in (ROOT / "desktop/build_worker.py").read_text(encoding="utf-8")
    assert (desktop / conf["build"]["frontendDist"]).resolve() == ROOT / "desktop/frontend"
    assert conf["build"]["beforeBuildCommand"] == "python prepare_frontend.py"
    csp = conf["app"]["security"]["csp"]
    assert "http:" not in csp.replace("http://ipc.localhost", "") and "https:" not in csp
    capability = json.loads((desktop / "capabilities/default.json").read_text(encoding="utf-8"))
    assert capability["permissions"] == [
        "core:default",
        "allow-heplab-invoke",
        "allow-heplab-cancel",
    ]
    manifest = (desktop / "Cargo.toml").read_text(encoding="utf-8")
    assert "plugin-shell" not in manifest and "plugin-fs" not in manifest
    core = (ROOT / "desktop/core/src/supervisor.rs").read_text(encoding="utf-8")
    assert "Command::new(&command.program)" in core and '"sh"' not in core and "cmd.exe" not in core


def test_worker_module_runs_as_subprocess_without_a_shell(tmp_path):
    process = subprocess.run(
        [sys.executable, "-m", "heplab.desktop.worker", "--project-root", str(tmp_path)],
        input=request(1, "engine.capabilities") + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    hello, reply = (json.loads(line) for line in process.stdout.splitlines())
    assert hello["protocol"] == worker.PROTOCOL and reply["ok"] is True


def test_packaged_worker_allows_only_samples_present_in_build():
    validate_library({"ok": True, "result": []}, set())
    validate_library(
        {"ok": True, "result": [{"id": "cms-run2016g"}, {"id": "cms-dy-ul16"}]},
        {"cms-run2016g", "cms-dy-ul16"},
    )
    with pytest.raises(SystemExit, match="packaged CMS datasets are unavailable"):
        validate_library({"ok": True, "result": []}, {"cms-run2016g"})
