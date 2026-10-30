"""Local read-only artifact API and guarded run submission."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path


def create_app(artifact_dir: str | Path = "artifacts"):
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("the local API requires FastAPI; install `heplab[serve]`") from exc
    from ..catalog import list_datasets

    root = Path(artifact_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    from .workbench import Jobs, RunConfig

    jobs = Jobs(root)
    from .data_workspace import operation_handlers

    data_closers: list = []
    data_handlers = operation_handlers(root.parent, data_closers)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        jobs.close()
        for close in data_closers:
            close()

    app = FastAPI(title="HEPLab simulator", version="0.1.0", lifespan=lifespan)
    app.state.jobs = jobs
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import JSONResponse

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def origin_guard(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in {
            f"http://{request.headers.get('host')}",
            f"https://{request.headers.get('host')}",
        }:
            return JSONResponse({"detail": "untrusted origin"}, status_code=403)
        if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            import secrets

            if not secrets.compare_digest(request.headers.get("x-heplab-token", ""), jobs.token):
                return JSONResponse({"detail": "session token required"}, status_code=403)
            body = bytearray()
            async for chunk in request.stream():
                budget = 65_536 if request.url.path.startswith("/api/v1/data/") else 16_384
                if len(body) + len(chunk) > budget:
                    return JSONResponse({"detail": "request budget exceeded"}, status_code=413)
                body.extend(chunk)
            # Starlette's cached request replays this bounded body downstream.
            request._body = bytes(body)
        response = await call_next(request)
        # The workbench holds a live session token; never let another site frame it.
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        return response

    from fastapi import Body, Header
    from pydantic import ValidationError
    from starlette.responses import FileResponse

    job_body = Body(...)
    job_key = Header(default=None, alias="Idempotency-Key")

    @app.get("/api/v1/data/library")
    def data_library():
        return data_handlers["data.library"]()

    @app.post("/api/v1/data/{operation}")
    def data_operation(operation: str, body: dict = job_body):
        from ..desktop.worker import RequestError, validate

        try:
            _, name, args = validate(
                {"id": 0, "op": "data." + operation, "args": body}, root.parent
            )
            return data_handlers[name](**args)
        except (ValueError, KeyError, TypeError, OSError, RequestError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/session")
    def session():
        from ..physics.constants import constants_record
        from ..physics.engine import capabilities
        from ..sim.pipeline import capabilities as simulation_capabilities

        simulation = simulation_capabilities()

        return JSONResponse(
            {
                "token": jobs.token,
                "engine": capabilities(),
                "simulation": simulation,
                "constants": constants_record(),
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/v1/project/overview")
    def project_overview():
        """Public, read-only status summary for the project overview website."""
        from .project import overview

        return JSONResponse(overview(), headers={"Cache-Control": "public, max-age=60"})

    @app.get("/api/v1/project/evidence")
    def project_evidence():
        """Small public evidence excerpt; detailed payloads remain in the repo."""
        from .project import evidence

        return JSONResponse(evidence(), headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/v1/detector")
    def detector_geometry():
        from ..physics.detector import geometry

        return geometry()

    @app.get("/api/v1/detector/display")
    def cms_display_manifest():
        from ..physics.cms_sources import display_manifest

        return display_manifest()

    @app.get("/api/v1/detector/display/{layer_id}")
    def cms_display_asset(layer_id: str):
        from ..physics.cms_sources import display_asset

        try:
            path = display_asset(layer_id)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/octet-stream")

    @app.get("/api/v1/calibration")
    def calibration_report():
        from ..physics.calibration import REFERENCE

        records = {}
        for name in (
            "silicon-calibration",
            "muon-response-calibration",
            "cms-field-validation",
            "cms-measured-validation",
            "cms-mass-calibration",
        ):
            path = REFERENCE / (name + ".json")
            records[name] = (
                json.loads(path.read_text(encoding="utf8"))
                if path.is_file()
                else {"status": "unavailable"}
            )
        return records

    @app.post("/api/v1/jobs", status_code=202)
    def submit_job(body: dict = job_body, idempotency_key: str | None = job_key):
        try:
            identity = jobs.submit(RunConfig.model_validate(body), idempotency_key)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": identity, "status": jobs.get(identity)["status"]}

    @app.post("/api/v1/preview")
    def preview_event(body: dict = job_body):
        from .workbench import preview

        try:
            return preview(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/lifetime")
    def lifetime_experiment(body: dict):
        from .workbench import lifetime_experiment as run_lifetime

        try:
            return run_lifetime(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/export-html")
    def export_result_html(body: dict):
        from ..export.web_page import render

        try:
            return {"html": render(body["result"])}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/jobs/{identity}")
    def get_job(identity: str):
        try:
            return jobs.get(identity)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown job") from exc

    @app.get("/api/v1/jobs")
    def list_jobs():
        return jobs.list()

    @app.post("/api/v1/jobs/{identity}/cancel")
    def cancel_job(identity: str):
        try:
            jobs.cancel(identity)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown job") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"id": identity, "cancellation_requested": True}

    @app.get("/api/v1/jobs/{identity}/events/{index}")
    def job_event(identity: str, index: int):
        try:
            return jobs.event(identity, index)
        except (KeyError, ValueError, StopIteration, OSError) as exc:
            raise HTTPException(status_code=404, detail="unknown event") from exc

    @app.get("/")
    def workbench():
        return FileResponse(
            Path(__file__).parent / "static" / "index.html", headers={"Cache-Control": "no-store"}
        )

    @app.get("/workbench")
    def local_workbench():
        return FileResponse(
            Path(__file__).parent / "static" / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/ui/{asset}")
    def ui_asset(asset: str):
        if asset not in {
            "workbench.css",
            "workbench.js",
            "event-display-gl.js",
            "detector-cutaway.js",
            "data-workspace.js",
            "intro.min.js",
            "introjs.min.css",
            "heplab-detector.png",
        }:
            raise HTTPException(status_code=404, detail="unknown UI asset")
        return FileResponse(
            Path(__file__).parent / "static" / asset, headers={"Cache-Control": "no-store"}
        )

    def artifact_path(run_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", run_id):
            raise HTTPException(status_code=404, detail="unknown artifact ID")
        path = root / f"{run_id}.json"
        if path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise HTTPException(status_code=404, detail="unknown artifact ID")
        return path

    @app.get("/api/v1/datasets")
    def datasets():
        return [manifest for manifest, _ in list_datasets()]

    @app.get("/api/v1/runs")
    def runs():
        from .workbench import run_summaries

        return run_summaries(root)

    @app.get("/api/v1/runs/{run_id}")
    def run(run_id: str):
        path = artifact_path(run_id)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="artifact is unreadable") from exc

    @app.get("/api/v1/runs/{run_id}/artifacts")
    def artifacts(run_id: str):
        return run(run_id)

    @app.get("/api/v1/events/{dataset}")
    def event(dataset: str, n: int = 1):
        from ..io.cache import cache_root, open_cached
        from ..io.xrootd import load_manifest

        try:
            manifest, _ = load_manifest(dataset)
            rows: list[dict] = []
            limit = max(0, min(n, 100))
            for marker in sorted(cache_root().glob("*/commit.json")):
                try:
                    descriptor = json.loads(marker.read_text(encoding="utf8"))
                    source = descriptor.get("source", {})
                    if source.get("dataset") == manifest.get("name", dataset):
                        rows.extend(open_cached(marker.parent.name)[: limit - len(rows)])
                except (OSError, ValueError, AttributeError):
                    continue  # foreign or damaged cache entries are not this dataset's events
                if len(rows) >= limit:
                    break
            if not rows and limit:
                raise FileNotFoundError("no committed cache chunks for this dataset")
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return rows[: max(0, min(n, 100))]

    @app.get("/api/v1/closure/{data_id}/{sim_id}")
    def closure(data_id: str, sim_id: str):
        from ..analyses.closure import compare

        try:
            return compare(artifact_path(data_id), artifact_path(sim_id))
        except (OSError, KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
