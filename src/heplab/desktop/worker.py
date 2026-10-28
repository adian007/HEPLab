"""Packaged desktop worker: bounded JSON-lines IPC over stdin/stdout.

The desktop shell launches this worker with a fixed argument vector (never a
shell) and a writable project root. It announces the protocol and version, then
answers one request per line. Only operations in ``operations.json`` exist; all
paths are relative to the project root and must stay inside it. The shell
validates requests with the same table, so this is the second of two checks.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import IO

from .. import __version__

SPEC = json.loads((Path(__file__).parent / "operations.json").read_text(encoding="utf-8"))
PROTOCOL = SPEC["protocol"]
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class RequestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def hello() -> dict:
    return {
        "protocol": PROTOCOL,
        "worker_version": __version__,
        "operations": sorted(SPEC["operations"]),
    }


def project_path(root: Path, value: str, access: str) -> Path:
    pure = PurePosixPath(value)
    if (
        "\\" in value
        or "\x00" in value
        or pure.is_absolute()
        or ":" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise RequestError("path_rejected", "paths must be plain relative paths in the project")
    candidate = root.joinpath(*pure.parts)
    for parent in [candidate, *candidate.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise RequestError("path_rejected", "symbolic links are not followed")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise RequestError("path_rejected", "path leaves the project root")
    if access == "read" and not resolved.is_file():
        raise RequestError("not_found", f"{value} does not exist")
    if access == "create" and resolved.exists():
        raise RequestError("exists", f"{value} already exists; outputs are immutable")
    return resolved


def validate(message: object, root: Path) -> tuple[int, str, dict]:
    if not isinstance(message, dict) or set(message) != {"id", "op", "args"}:
        raise RequestError("malformed", "request must be exactly {id, op, args}")
    identity, op, args = message["id"], message["op"], message["args"]
    if not isinstance(identity, int) or isinstance(identity, bool) or identity < 0:
        raise RequestError("malformed", "id must be a non-negative integer")
    spec = SPEC["operations"].get(op) if isinstance(op, str) else None
    if spec is None:
        raise RequestError("unknown_operation", f"unknown operation {op!r}")
    if not isinstance(args, dict) or set(args) - set(spec["args"]):
        raise RequestError("invalid_arguments", "unexpected arguments")
    checked: dict = {}
    for name, rule in spec["args"].items():
        if name not in args:
            if not rule.get("optional"):
                raise RequestError("invalid_arguments", f"missing argument {name}")
            continue
        value = args[name]
        if rule["type"] in {"id", "path"}:
            if not isinstance(value, str) or len(value) > SPEC["max_string_chars"]:
                raise RequestError("invalid_arguments", f"{name} must be a bounded string")
            if rule["type"] == "id" and not IDENTIFIER.fullmatch(value):
                raise RequestError("invalid_arguments", f"{name} is not a valid identifier")
            checked[name] = (
                project_path(root, value, rule["access"]) if rule["type"] == "path" else value
            )
        elif rule["type"] == "object":
            # Structure only; the operation validates contents against its own model.
            if not isinstance(value, dict):
                raise RequestError("invalid_arguments", f"{name} must be an object")
            checked[name] = value
        else:
            integer = rule["type"] == "integer"
            allowed = int if integer else (int, float)
            if not isinstance(value, allowed) or isinstance(value, bool):
                kind = "an integer" if integer else "a number"
                raise RequestError("invalid_arguments", f"{name} must be {kind}")
            if not math.isfinite(value) or not rule["min"] <= value <= rule["max"]:
                raise RequestError("invalid_arguments", f"{name} is out of range")
            checked[name] = value if integer else float(value)
    return identity, op, checked


def operations(root: Path, closers: list | None = None) -> dict[str, Callable[..., object]]:
    artifacts = root / "artifacts"

    def calibration_report():
        from ..physics.calibration import REFERENCE

        names = (
            "silicon-calibration",
            "muon-response-calibration",
            "cms-field-validation",
            "cms-measured-validation",
            "cms-mass-calibration",
        )
        return {
            name: json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
            if (REFERENCE / f"{name}.json").is_file()
            else {"status": "unavailable"}
            for name in names
        }

    def run_get(run_id: str):
        path = artifacts / f"{run_id}.json"
        if path.is_symlink() or path.resolve().parent != artifacts.resolve() or not path.is_file():
            raise RequestError("not_found", "unknown artifact ID")
        return json.loads(path.read_text(encoding="utf-8"))

    def lab_profile(profile: Path):
        from ..lab.profile import load_profile, profile_summary

        return profile_summary(load_profile(profile))

    def lab_replay(profile: Path, raw: Path, output: Path, **options):
        from ..lab.replay import replay

        record = replay(
            profile,
            raw,
            output,
            offsets_path=options.get("offsets"),
            window_ns=options.get("window_ns", 25.0),
            trigger_source=options.get("trigger_source"),
        )
        return {"output": output.relative_to(root).as_posix(), "record": record}

    def engine_capabilities():
        from ..physics.engine import capabilities

        return capabilities()

    def detector_geometry():
        from ..physics.detector import geometry

        return geometry()

    def datasets_list():
        from ..catalog import list_datasets

        return [manifest for manifest, _ in list_datasets()]

    def project_overview():
        from ..server.project import overview

        return overview()

    def project_evidence():
        from ..server.project import evidence

        return evidence()

    # The simulator job engine is the same one the web workbench uses.
    engine: dict = {}

    def jobs():
        if "jobs" not in engine:
            from ..server.workbench import Jobs

            artifacts.mkdir(parents=True, exist_ok=True)
            engine["jobs"] = Jobs(artifacts)
            if closers is not None:
                closers.append(engine["jobs"].close)
        return engine["jobs"]

    def workbench_session():
        from ..physics.engine import capabilities
        from ..sim.pipeline import runtime

        try:
            simulation = {"available": True, "versions": runtime()["inventory"]["versions"]}
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            simulation = {"available": False, "reason": str(exc)}
        # The workbench enables Run only once it holds a session token. Over
        # desktop IPC the channel itself is the authority, so this is a fixed
        # marker that is never checked or sent anywhere.
        return {"token": "desktop-ipc", "engine": capabilities(), "simulation": simulation}

    def detector_display():
        from ..physics.cms_sources import display_manifest

        return display_manifest()

    def job_submit(config: dict, idempotency_key: str | None = None):
        from pydantic import ValidationError

        from ..server.workbench import RunConfig

        try:
            run = RunConfig.model_validate(config)
        except ValidationError as exc:
            raise RequestError("invalid_arguments", str(exc)) from exc
        try:
            identity = jobs().submit(run, idempotency_key)
        except ValueError as exc:
            raise RequestError("conflict", str(exc)) from exc
        return {"id": identity, "status": jobs().get(identity)["status"]}

    def known(call):
        def wrapped(**args):
            try:
                return call(**args)
            except KeyError as exc:
                raise RequestError("not_found", "unknown job") from exc

        return wrapped

    def job_cancel(job_id: str):
        jobs().cancel(job_id)
        return {"id": job_id, "cancellation_requested": True}

    def job_event(job_id: str, index: int):
        try:
            return jobs().event(job_id, index)
        except (ValueError, StopIteration) as exc:
            raise RequestError("not_found", "unknown event") from exc

    return {
        "workbench.session": workbench_session,
        "detector.display": detector_display,
        "jobs.submit": job_submit,
        "jobs.get": known(lambda job_id: jobs().get(job_id)),
        "jobs.cancel": known(job_cancel),
        "jobs.event": known(job_event),
        "project.overview": project_overview,
        "project.evidence": project_evidence,
        "engine.capabilities": engine_capabilities,
        "calibration.report": calibration_report,
        "detector.geometry": detector_geometry,
        "datasets.list": datasets_list,
        "runs.list": lambda: [
            {"id": p.stem, "artifact": p.name} for p in sorted(artifacts.glob("*.json"))
        ],
        "runs.get": run_get,
        "lab.profile": lab_profile,
        "lab.replay": lab_replay,
    }


def respond(stream: IO[str], value: dict) -> None:
    line = json.dumps(value, allow_nan=False, separators=(",", ":"))
    if len(line.encode()) > SPEC["max_response_bytes"]:
        line = json.dumps(
            {
                "id": value.get("id"),
                "ok": False,
                "error": {"code": "response_too_large", "message": "result exceeds IPC budget"},
            }
        )
    stream.write(line + "\n")
    stream.flush()


def serve(root: Path, stdin: IO[str], stdout: IO[str]) -> int:
    closers: list = []
    handlers = operations(root, closers)
    if set(handlers) != set(SPEC["operations"]):
        raise AssertionError("worker handlers disagree with operations.json")
    respond(stdout, hello())
    limit = SPEC["max_request_bytes"]
    while True:
        line = stdin.readline(limit + 1)
        if not line:
            # The shell closed the channel: cancel running simulations, then exit.
            for close in closers:
                close()
            return 0
        identity = None
        try:
            if len(line.encode()) > limit or not line.endswith("\n"):
                # Drain the rest of an oversized line so the stream stays framed.
                while line and not line.endswith("\n"):
                    line = stdin.readline(limit + 1)
                raise RequestError("too_large", "request exceeds IPC budget")
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RequestError("malformed", "request is not JSON") from exc
            if isinstance(message, dict) and isinstance(message.get("id"), int):
                identity = message["id"]
            identity, op, args = validate(message, root)
            respond(stdout, {"id": identity, "ok": True, "result": handlers[op](**args)})
        except RequestError as exc:
            respond(
                stdout,
                {"id": identity, "ok": False, "error": {"code": exc.code, "message": str(exc)}},
            )
        except (ValueError, LookupError, OSError, RuntimeError, TypeError) as exc:
            respond(
                stdout,
                {
                    "id": identity,
                    "ok": False,
                    "error": {
                        "code": "operation_failed",
                        "message": f"{type(exc).__name__}: {exc}",
                    },
                },
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heplab-worker")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    if not root.is_dir():
        print(f"heplab-worker: project root {root} is not a directory", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    return serve(root, sys.stdin, sys.stdout)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
