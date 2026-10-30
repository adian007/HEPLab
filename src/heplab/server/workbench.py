"""Local simulator jobs. Fixed operations only; no executable or path submission."""

from __future__ import annotations

import json
import math
import re
import secrets
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import __version__
from ..io.artifacts import publish
from ..io.provenance import config_hash
from ..physics.calibration import muon_response_parameters
from ..physics.constants import MUON_MASS_GEV
from ..physics.detector import geometry, silicon_stopping_power, tracker_trajectory, trajectory
from ..physics.engine import execute
from ..physics.lifetime import path_from_altitudes_m, run_survival_experiment
from ..physics.models import display_model_spec, model_spec_for_run
from ..physics.reference import FourVector, TrackState, addressed_uniform


def muon_display(muons, event=0, *, model_ids=None):
    model_ids = model_ids or ["recorded-nanoaod-ideal-display-v1"]
    tracks = []
    for muon in muons or []:
        eta, phi = muon["eta"], muon["phi"]
        state = TrackState(
            (0.0, 0.0, 0.0),
            FourVector.from_pt_eta_phi_mass(muon["pt"], eta, phi, MUON_MASS_GEV),
            muon["charge"],
            0.0,
        )
        traced = trajectory(state)
        tracks.append(
            {
                "object_id": muon["object_id"],
                "pdg_id": 13 if muon["charge"] < 0 else -13,
                "charge": muon["charge"],
                "detector": muon,
                "model_ids": list(model_ids),
                "points": traced["points"],
                "trajectory": traced,
            }
        )
    display_spec = (
        display_model_spec() if model_ids == ["recorded-nanoaod-ideal-display-v1"] else None
    )
    return {
        "event": event,
        "tracks": tracks,
        "geometry": geometry(),
        **({"display_model_spec": display_spec} if display_spec else {}),
        "display": (
            "IP-assumed ideal-solenoid extrapolation of reconstructed muons; "
            "crossings are predictions, not measured hits"
        ),
    }


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    mode: str = Field(default="analytic", pattern="^(analytic|pythia)$")
    backend: str = Field(default="reference", pattern="^(reference|rust|delphes)$")
    seed: int = Field(default=42, ge=1, le=900_000_000)
    events: int = Field(default=100, ge=1, le=1000)
    momentum_gev: float = Field(default=45.0, ge=1, le=100)
    bz_tesla: float = Field(default=3.8, ge=-8, le=8)
    thickness_mm: float = Field(default=1.0, ge=0.1, le=5)
    noise_adc: float = Field(default=1.0, ge=0, le=10)
    threshold_adc: float = Field(default=5.0, ge=0, le=100)
    response_model: str = Field(default="ideal", pattern="^(ideal|delphes_reference)$")
    field_model: str = Field(default="ideal_bore", pattern="^(ideal_bore|cms_tracker)$")
    source_model: str = Field(
        default="transverse_pair", pattern="^(transverse_pair|angular_sample)$"
    )
    muon_pt_min_gev: float = Field(default=20.0, ge=0, le=500)
    muon_abs_eta_max: float = Field(default=2.4, gt=0, le=2.4)
    muon_iso_max: float = Field(default=0.15, ge=0, le=10)
    mass_min_gev: float = Field(default=60.0, ge=0, le=1000)
    mass_max_gev: float = Field(default=120.0, gt=0, le=1000)

    @model_validator(mode="before")
    @classmethod
    def migrate_config_envelope(cls, value):
        """Accept a split v2 config and the legacy flat v1 request explicitly."""
        if not isinstance(value, dict) or "schema" not in value:
            return value
        if value.get("schema") != "heplab-run-config-v2":
            raise ValueError("unsupported run configuration schema")
        domains = {
            "run": {"mode", "backend", "seed", "events"},
            "analytic": {
                "momentum_gev",
                "bz_tesla",
                "thickness_mm",
                "noise_adc",
                "threshold_adc",
                "field_model",
                "source_model",
            },
            "collision": {"response_model"},
            "display": {"projection", "region"},
            "analysis": {
                "muon_pt_min_gev",
                "muon_abs_eta_max",
                "muon_iso_max",
                "mass_min_gev",
                "mass_max_gev",
            },
        }
        if set(value) != {"schema", *domains}:
            raise ValueError(
                "v2 configuration must contain run, analytic, collision, "
                "display, and analysis groups"
            )
        flat = {}
        for domain, allowed in domains.items():
            parameters = value[domain]
            if not isinstance(parameters, dict) or set(parameters) - allowed:
                raise ValueError(f"invalid {domain} configuration group")
            if domain != "display":
                flat.update(parameters)
            elif parameters and (
                parameters.get("projection", "xy-xz") not in ("xy-xz", "xy", "xz", "3d")
                or parameters.get("region", "cms") not in ("tracker", "pixel", "solenoid", "cms")
            ):
                raise ValueError("invalid display configuration group")
        return flat

    def to_envelope(self, *, projection: str = "xy-xz", region: str = "cms") -> dict:
        """Serialize the current flat runtime config as the v2 grouped setup contract."""
        values = self.model_dump()

        def take(names):
            return {name: values[name] for name in names}

        return {
            "schema": "heplab-run-config-v2",
            "run": take(("mode", "backend", "seed", "events")),
            "analytic": take(
                (
                    "momentum_gev",
                    "bz_tesla",
                    "thickness_mm",
                    "noise_adc",
                    "threshold_adc",
                    "field_model",
                    "source_model",
                )
            ),
            "collision": take(("response_model",)),
            "display": {"projection": projection, "region": region},
            "analysis": take(
                (
                    "muon_pt_min_gev",
                    "muon_abs_eta_max",
                    "muon_iso_max",
                    "mass_min_gev",
                    "mass_max_gev",
                )
            ),
        }

    @model_validator(mode="after")
    def compatible_backend(self) -> Self:
        if self.mass_min_gev >= self.mass_max_gev:
            raise ValueError("dimuon mass window must have increasing bounds")
        if self.field_model == "cms_tracker" and (self.mode != "analytic" or self.bz_tesla != 3.8):
            raise ValueError("CMS tracker field requires analytic bench and fixed nominal B=3.8 T")
        if (self.mode == "pythia") != (self.backend == "delphes"):
            raise ValueError(
                "collision mode requires delphes; analytic mode requires reference or rust"
            )
        if self.response_model == "delphes_reference" and (
            self.mode != "analytic" or self.momentum_gev < 5
        ):
            raise ValueError(
                "reference response is a separate bench branch requiring momentum >=5 GeV"
            )
        if self.mode == "analytic" and self.source_model == "angular_sample":
            if self.events > 200:
                raise ValueError("angular samples are limited to 200 events per run")
            if self.response_model == "delphes_reference" and self.momentum_gev < 5 * math.cosh(
                2.4
            ):
                raise ValueError("angular response samples need |p| >=27.8 GeV to keep pT >=5 GeV")
        return self


def bench(
    config: RunConfig,
    cancel: threading.Event,
    event: int = 0,
    direction: tuple[float, float, float] | None = None,
) -> dict:
    """Two declared back-to-back muons, not a collision event generator.

    ``direction`` overrides the source direction (live preview aiming only).
    """
    tracks = []
    run_model_spec = model_spec_for_run(config)
    model_ids = [component["id"] for component in run_model_spec["components"]]
    if direction is None and config.source_model == "angular_sample":
        address: dict[str, Any] = dict(
            master_seed=config.seed,
            event_key=f"bench-{event}",
            object_id=0,
            counter=0,
            correlation_group="nominal",
            model_id="angular-pair-v1",
        )
        cosine = (2 * addressed_uniform(**address, stage_id="cos_theta") - 1) * math.tanh(2.4)
        phi = 2 * math.pi * addressed_uniform(**address, stage_id="phi")
        sine = math.sqrt(1 - cosine * cosine)
        direction = (sine * math.cos(phi), sine * math.sin(phi), cosine)
    elif direction is None:
        direction = (1.0, 0.0, 0.0)
    for identity, charge in enumerate((-1, 1)):
        if cancel.is_set():
            raise RuntimeError("run cancelled")
        p = config.momentum_gev
        state = TrackState(
            (0, 0, 0),
            FourVector(math.hypot(p, MUON_MASS_GEV), *(charge * p * x for x in direction)),
            charge,
            0,
        )
        before = (
            tracker_trajectory(state, 1.0, config.backend)
            if config.field_model == "cms_tracker"
            else trajectory(state, bz=config.bz_tesla, max_path=1.0, backend=config.backend)
        )
        stopping_power, material_reference = silicon_stopping_power(
            state.momentum.energy - MUON_MASS_GEV
        )
        arrival = (
            before["state"]
            if config.field_model == "cms_tracker"
            else execute(
                {
                    "op": "propagate",
                    "state": asdict(state),
                    "path_length_m": 1.0,
                    "bz_tesla": config.bz_tesla,
                },
                backend=config.backend,
            )
        )
        address = {
            "master_seed": config.seed,
            "event_key": f"bench-{event}",
            "object_id": identity,
            "stage_id": "material",
            "counter": 0,
            "correlation_group": "nominal",
            "model_id": "bench-v1",
        }
        slab = {
            "id": "illustrative-silicon",
            "thickness_m": config.thickness_mm / 1000,
            "radiation_length_m": 0.0937,
            "stopping_power_gev_per_m": stopping_power,
            "min_beta_gamma": 1.0,
            "max_beta_gamma": 1000.0,
            "scatter": True,
        }
        material = execute(
            {"op": "material", "state": arrival, "slab": slab, "address": address},
            backend=config.backend,
        )
        outgoing = material["state"]
        outgoing_state = TrackState(
            tuple(outgoing["position"]),
            FourVector(**outgoing["momentum"]),
            outgoing["charge"],
            outgoing["time_ns"],
        )
        offset = 1.0 + config.thickness_mm / 1000.0
        after = (
            tracker_trajectory(outgoing_state, 16.0 - offset, config.backend)
            if config.field_model == "cms_tracker"
            else trajectory(
                outgoing_state, bz=config.bz_tesla, max_path=16.0 - offset, backend=config.backend
            )
        )
        traced = {
            **after,
            "points": before["points"] + after["points"],
            "path_m": before["path_m"] + [offset + s for s in after["path_m"]],
            "crossings": before["crossings"]
            + [{**c, "path_m": offset + c["path_m"]} for c in after["crossings"]],
            "field_exit_path_m": (
                offset + after["field_exit_path_m"]
                if after["field_exit_path_m"] is not None
                else None
            ),
            "model": (
                "cms-tracker-oae-with-single-silicon-slab-v1"
                if config.field_model == "cms_tracker"
                else "ideal-solenoid-with-single-silicon-slab-v1"
            ),
        }
        points = traced["points"]
        electronics = {
            "gain_adc_per_gev": 100000.0,
            "pedestal_adc": 0.0,
            "noise_sigma_adc": config.noise_adc,
            "threshold_adc": config.threshold_adc,
            "saturation_adc": 255.0,
        }
        digit = execute(
            {
                "op": "digitize",
                "deposit_gev": material["deposit_gev"],
                "config": electronics,
                "address": address,
            },
            backend=config.backend,
        )
        reference_response = None
        if config.response_model == "delphes_reference":
            pt = math.hypot(state.momentum.px, state.momentum.py)
            parameters = muon_response_parameters(pt, math.asinh(state.momentum.pz / pt))
            sampled = execute(
                {
                    "op": "simulate",
                    "particles": [{"object_id": identity, "state": asdict(state)}],
                    "config": {
                        "seed": config.seed,
                        "event_key": f"bench-{event}",
                        "efficiency": parameters["efficiency"],
                        "relative_pt_resolution": parameters["relative_pt_resolution"],
                        "momentum_scale": parameters["momentum_scale"],
                        "path_length_m": 0.0,
                        "bz_tesla": 0.0,
                        "max_objects": 2,
                    },
                },
                backend=config.backend,
            )
            reference_response = {
                "parameters": parameters,
                "sample": sampled,
                "scope": "independent truth-to-object branch; not reapplied to DELPHES",
            }
        tracks.append(
            {
                "object_id": identity,
                "pdg_id": 13 if charge < 0 else -13,
                "charge": charge,
                "model_ids": model_ids,
                "points": points,
                "truth": asdict(state),
                "material": material,
                "digit": digit,
                "trajectory": traced,
                "material_reference": material_reference,
                "reference_response": reference_response,
            }
        )
    return {
        "mode": "analytic",
        "backend": config.backend,
        "validation": "educational_unvalidated",
        "model_spec": run_model_spec,
        "event": event,
        "events": 1,
        "source": (
            "isotropic back-to-back muon directions within |eta|<2.4; fixed momentum; no collisions"
            if config.source_model == "angular_sample"
            else "declared back-to-back muon test fixture"
        ),
        "geometry": geometry(config.field_model),
        "display": (
            (
                "CMS nominal OAE tracker field; stops at validity edge; 5 mm "
                "polyline crossings; single illustrative silicon slab"
            )
            if config.field_model == "cms_tracker"
            else (
                "Ideal-solenoid trajectory with one PDG-calibrated silicon slab at "
                "1 m path; other surfaces have no material; predicted crossings"
            )
        ),
        "tracks": tracks,
        "config": config.model_dump(),
    }


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    config: RunConfig
    event: int = Field(default=0, ge=0, le=199)
    eta: float | None = Field(default=None, ge=-2.4, le=2.4)
    phi: float | None = Field(default=None, ge=-math.pi, le=math.pi)

    @model_validator(mode="after")
    def bench_only(self) -> Self:
        if self.config.mode != "analytic":
            raise ValueError("live preview supports the analytic bench only")
        if (self.eta is None) != (self.phi is None):
            raise ValueError("aiming the source needs both eta and phi")
        if self.config.response_model == "delphes_reference" and self.eta is not None:
            if abs(self.eta) >= 2.4:
                raise ValueError("reference response requires |eta| < 2.4")
            if self.config.momentum_gev / math.cosh(self.eta) < 5.0:
                raise ValueError("aimed reference response requires pT >= 5 GeV")
        return self


def preview(request: dict) -> dict:
    """One bench event computed on demand for the live display; never persisted.

    Same physics path as a submitted run. The result carries ``preview: true``
    and no run identity, so it cannot be mistaken for a saved artifact.
    """
    value = PreviewRequest.model_validate(request)
    direction = None
    if value.eta is not None and value.phi is not None:
        theta = 2 * math.atan(math.exp(-value.eta))
        direction = (
            math.sin(theta) * math.cos(value.phi),
            math.sin(theta) * math.sin(value.phi),
            math.cos(theta),
        )
    event = bench(value.config, threading.Event(), value.event, direction=direction)
    event.update(preview=True, events=1, config=value.config.model_dump())
    if direction is not None:
        event["source"] = (
            f"live aimed back-to-back muon pair at eta={value.eta:+.3f}, "
            f"phi={value.phi:+.3f} rad; preview only, not saved"
        )
    return event


class LifetimeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    path_mode: str = Field(default="fixed", pattern="^(fixed|altitude)$")
    momentum_gev_c: float = Field(default=1.0, gt=0, le=1000)
    path_length_m: float = Field(default=15.0, ge=0, le=1_000_000)
    production_altitude_km: float = Field(default=15.0, gt=0, le=100)
    detector_altitude_km: float = Field(default=0.0, ge=0, le=10)
    zenith_deg: float = Field(default=0.0, ge=0, lt=75)
    seed: int = Field(default=42, ge=1, le=900_000_000)
    sample_size: int = Field(default=10_000, ge=100, le=100_000)

    @model_validator(mode="after")
    def altitude_order(self) -> Self:
        if (
            self.path_mode == "altitude"
            and self.production_altitude_km <= self.detector_altitude_km
        ):
            raise ValueError("production altitude must be above detector altitude")
        return self


def lifetime_experiment(request: dict) -> dict:
    """Run the separate fixed-momentum muon survival teaching experiment."""
    value = LifetimeRequest.model_validate(request)
    path = (
        value.path_length_m
        if value.path_mode == "fixed"
        else path_from_altitudes_m(
            value.production_altitude_km * 1000,
            value.detector_altitude_km * 1000,
            math.radians(value.zenith_deg),
        )
    )
    result = run_survival_experiment(
        momentum_gev_c=value.momentum_gev_c,
        path_length_m=path,
        seed=value.seed,
        sample_size=value.sample_size,
    )
    result["config"].update(
        {
            "path_mode": value.path_mode,
            "production_altitude_km": value.production_altitude_km
            if value.path_mode == "altitude"
            else None,
            "detector_altitude_km": value.detector_altitude_km
            if value.path_mode == "altitude"
            else None,
            "zenith_deg": value.zenith_deg if value.path_mode == "altitude" else None,
        }
    )
    result["model_spec"]["domain"]["path_source"] = (
        "plane-parallel altitude geometry only; no atmospheric material"
        if value.path_mode == "altitude"
        else "user-declared fixed flight path"
    )
    digest = config_hash(
        {
            "schema": result["schema"],
            "config": result["config"],
            "summary": result["summary"],
            "model_spec": result["model_spec"],
        }
    )
    result["result_sha256"] = digest
    result["artifact"] = {
        "format": "heplab-lifetime-artifact-v1",
        "schema": "heplab-run-artifact-v1",
        "scope": "full_run",
        "run_id": digest[:24],
        "config_sha256": config_hash(result["config"]),
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_ids": [result["model_spec"]["id"]],
        "heplab_version": __version__,
        "parent_run_sha256": None,
    }
    return result


def analyze_events(events: list[dict]) -> dict:
    """Compact unweighted observables; trajectories are stored separately per event."""
    samples, pairs = [], []
    for event in events:
        response_vectors = []
        truth_vectors = []
        for track in event["tracks"]:
            p = FourVector(**track["truth"]["momentum"])
            truth_vectors.append(p)
            pt = math.hypot(p.px, p.py)
            response = track["reference_response"]
            objects = response["sample"]["objects"] if response else []
            measured = FourVector(**objects[0]["state"]["momentum"]) if objects else None
            if measured:
                response_vectors.append(measured)
            samples.append(
                {
                    "event": event["event"],
                    "object_id": track["object_id"],
                    "pt_gev": pt,
                    "eta": math.asinh(p.pz / pt),
                    "deposit_mev": track["material"]["deposit_gev"] * 1000,
                    "adc": track["digit"]["adc"],
                    "digit_accepted": track["digit"]["accepted"],
                    "response_pt_gev": math.hypot(measured.px, measured.py) if measured else None,
                    "response_status": "accepted"
                    if measured
                    else "lost"
                    if response
                    else "not_requested",
                    "energy_residual_gev": track["material"]["energy_residual_gev"],
                }
            )
        pairs.append(
            {
                "event": event["event"],
                "truth_mass_gev": (truth_vectors[0] + truth_vectors[1]).physical_mass,
                "response_mass_gev": (response_vectors[0] + response_vectors[1]).physical_mass
                if len(response_vectors) == 2
                else None,
            }
        )
    return {
        "scope": "unweighted declared muon sample; not collision data or CMS calibration",
        "events": len(events),
        "particles": len(samples),
        "samples": samples,
        "pairs": pairs,
    }


def _event_view(parent: dict, index: int, overlay: dict | None = None) -> dict:
    """Return a selected-event display view linked to its immutable run result."""
    value = {**parent, **(overlay or {})}
    parent_artifact = parent.get("artifact") or {}
    parent_digest = parent_artifact.get("result_sha256")
    if not parent_digest:
        parent_digest = config_hash(
            {
                key: item
                for key, item in parent.items()
                if key not in {"artifact", "output_directory"}
            }
        )
    view_payload = {
        "event": index,
        "tracks": value.get("tracks", []),
        "event_info": value.get("event_info"),
        "geometry": value.get("geometry"),
        "display": value.get("display"),
        "model_spec": value.get("model_spec"),
    }
    value["artifact"] = {
        **parent_artifact,
        "format": "heplab-event-view-v1",
        "schema": "heplab-event-view-v1",
        "scope": "selected_event_view",
        "run_id": parent_artifact.get("run_id"),
        "event_index": index,
        "parent_run_sha256": parent_digest,
        "result_sha256": config_hash(view_payload),
    }
    value["view_scope"] = "selected event display; parent run analysis is identified separately"
    return value


def run_summaries(root: Path, limit: int = 200) -> list[dict]:
    """Saved runs, newest first, with the fields the run list labels need.

    Unreadable or foreign JSON keeps its id/artifact entry; opening it reports why.
    """
    paths = sorted(
        (p for p in root.glob("*.json") if p.is_file() and not p.is_symlink()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    rows = []
    for path in paths:
        row: dict[str, Any] = {"id": path.stem, "artifact": path.name}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = None
        if isinstance(value, dict):
            artifact = value.get("artifact")
            if not isinstance(artifact, dict):
                artifact = {}
            row.update(
                mode=value.get("mode"),
                created_utc=artifact.get("created_utc"),
                format=artifact.get("format"),
            )
            if isinstance(value.get("config"), dict):
                row["config"] = value["config"]
        rows.append(row)
    return rows


class Jobs:
    """Durable FIFO simulator queue: one run executes at a time, others wait.

    Records survive process restarts (see ``jobstore``). On start-up, runs left
    queued or running by a dead process are reclaimed and requeued; a run that
    was interrupted mid-execution twice is failed rather than retried forever.
    """

    MAX_PENDING = 16
    MAX_ATTEMPTS = 2
    RETAIN = 500
    RETAIN_SECONDS = 30 * 24 * 60 * 60
    PROGRESS_INTERVAL_S = 0.25

    def __init__(self, root: Path):
        from .jobstore import JobStore

        self.root = root
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="heplab-simulator")
        self.lock = threading.RLock()
        self.store = JobStore(root, secrets.token_hex(8))
        self.cancels: dict[str, threading.Event] = {}
        self.live: dict[str, dict[str, Any]] = {}
        self.flushed: dict[str, float] = {}
        self.closing = False
        self._recover()
        self._prune()

    def _prune(self) -> None:
        """Apply database retention and remove only artifacts owned by evicted jobs."""
        with self.lock:
            removed = self.store.prune(self.RETAIN, older_than=time.time() - self.RETAIN_SECONDS)
            root = self.root.resolve()
            for identity in removed:
                if not re.fullmatch(r"[a-f0-9]{24}", identity):
                    continue
                for path in (
                    self.root / f"{identity}.json",
                    self.root / f"{identity}-events",
                    self.root / f"{identity}-simulation",
                ):
                    if path.is_symlink() or path.resolve().parent != root:
                        continue
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.is_file():
                        path.unlink()
                for path in self.root.glob(f".interrupted-{identity}-simulation-*"):
                    if path.is_symlink() or path.resolve().parent != root:
                        continue
                    if path.is_dir():
                        shutil.rmtree(path)

    def _recover(self) -> None:
        with self.lock:
            for row in self.store.active():
                owner = row["owner"]
                if self.store.owner_alive(owner):
                    continue  # another live engine is running it
                crashed = row["status"] == "running"
                if crashed and row["attempts"] + 1 >= self.MAX_ATTEMPTS:
                    if self.store.claim(row["id"], owner, crashed=True):
                        self.store.update(
                            row["id"],
                            status="failed",
                            error="interrupted by worker restarts; resubmit to retry",
                        )
                    continue
                try:
                    config = RunConfig.model_validate(row["config"])
                except ValueError as exc:
                    if self.store.claim(row["id"], owner, crashed=crashed):
                        self.store.update(row["id"], status="failed", error=str(exc)[:2000])
                    continue
                if self.store.claim(row["id"], owner, crashed=crashed):
                    self.cancels[row["id"]] = threading.Event()
                    self.pool.submit(self._run, row["id"], config)

    def submit(self, config: RunConfig, idempotency_key: str | None = None) -> str:
        fingerprint = config_hash(config.model_dump())
        with self.lock:
            if idempotency_key is not None:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", idempotency_key):
                    raise ValueError("invalid idempotency key")
                prior = self.store.by_key(idempotency_key)
                if prior is not None:
                    if prior["fingerprint"] != fingerprint:
                        raise ValueError("idempotency key already belongs to different parameters")
                    return prior["id"]
            pending = sum(1 for row in self.store.active() if row["owner"] == self.store.owner)
            if pending >= self.MAX_PENDING:
                raise ValueError("job queue is full; wait for queued runs to finish")
            identity = secrets.token_hex(12)
            self.store.insert(identity, config.model_dump(), fingerprint, idempotency_key)
            self.cancels[identity] = threading.Event()
            self._prune()
        self.pool.submit(self._run, identity, config)
        return identity

    def _view(self, row: dict) -> dict:
        job: dict[str, Any] = {"id": row["id"], "status": row["status"], "config": row["config"]}
        for name in ("phase", "progress", "error"):
            if row.get(name) is not None:
                job[name] = row[name]
        if row["attempts"]:
            job["attempt"] = row["attempts"] + 1
        job.update(self.live.get(row["id"], {}))
        return job

    def get(self, identity):
        with self.lock:
            row = self.store.get(identity) if isinstance(identity, str) else None
            job = self._view(row) if row is not None else None
        if job is not None and job["status"] != "completed":
            return job
        # Completed results live in the published artifact (also covers runs that
        # predate the job store).
        if not re.fullmatch(r"[a-f0-9]{24}", identity):
            raise KeyError(identity)
        path = self.root / f"{identity}.json"
        if path.is_symlink() or not path.is_file():
            if job is not None:
                return {**job, "status": "failed", "error": "result artifact is missing"}
            raise KeyError(identity)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise KeyError(identity) from exc
        if (
            not isinstance(value, dict)
            or value.get("mode") not in {"analytic", "pythia"}
            or "config" not in value
        ):
            raise KeyError(identity)
        return {
            **(job or {}),
            "id": identity,
            "status": "completed",
            "config": value["config"],
            "result": value,
        }

    def list(self, limit: int = 50) -> list[dict]:
        """Recent jobs without results, newest first, so a reloaded UI can reattach."""
        with self.lock:
            return [self._view(row) for row in self.store.recent(limit)]

    def cancel(self, identity):
        with self.lock:
            row = self.store.get(identity) if isinstance(identity, str) else None
            if row is None:
                self.get(identity)  # finished legacy runs: a no-op, or KeyError if unknown
                return
            if row["status"] not in {"queued", "running"}:
                return
            if identity in self.cancels:
                self.cancels[identity].set()
                if row["status"] == "queued":
                    self.store.update(identity, status="cancelled")
                return
            if self.store.owner_alive(row["owner"]):
                raise ValueError("run belongs to another HEPLab process")
            if self.store.claim(identity, row["owner"], crashed=False):
                self.store.update(identity, status="cancelled")

    def _phase(self, identity: str, phase: str) -> None:
        with self.lock:
            self.live.setdefault(identity, {})["phase"] = phase
            self.store.update(identity, phase=phase)

    def _progress(self, identity: str, completed: int, total: int) -> None:
        progress = {"completed": completed, "total": total}
        now = time.monotonic()
        with self.lock:
            self.live.setdefault(identity, {})["progress"] = progress
            if completed == total or now - self.flushed.get(identity, 0.0) >= (
                self.PROGRESS_INTERVAL_S
            ):
                self.flushed[identity] = now
                self.store.update(identity, progress=progress)

    def _finish(self, identity: str, **fields: Any) -> None:
        with self.lock:
            self.store.update(identity, **fields)
            self.live.pop(identity, None)
            self.flushed.pop(identity, None)
            self.cancels.pop(identity, None)

    def event(self, identity, index):
        job = self.get(identity)
        if job["status"] != "completed" or not 0 <= index < 1000:
            raise ValueError("event unavailable")
        result = job["result"]
        if result["mode"] == "analytic":
            if not 0 <= index < result.get("events", 1):
                raise ValueError("event outside bench range")
            if index == 0:
                return _event_view(result, index)
            path = self.root / f"{identity}-events" / f"{index}.json"
            if path.parent.is_symlink() or path.is_symlink() or not path.is_file():
                raise ValueError("stored event unavailable")
            return _event_view(
                result,
                index,
                {**json.loads(path.read_text(encoding="utf-8")), "events": result["events"]},
            )
        if index >= result["summary"]["events"]:
            raise ValueError("event outside generated range")
        from ..readers.delphes import read

        native = next(
            read(
                self.root / (identity + "-simulation") / "events.root",
                entry_start=index,
                entry_stop=index + 1,
                include_truth=False,
            )
        )
        info = next(
            (
                row
                for row in result.get("analysis", {}).get("event_rows", [])
                if row["event"] == index
            ),
            None,
        )
        return _event_view(
            result,
            index,
            {
                **muon_display(
                    native["Muon"],
                    index,
                    model_ids=[item["id"] for item in result["model_spec"]["components"]],
                ),
                "event_info": info,
            },
        )

    def _run(self, identity, config):
        cancel = self.cancels.get(identity) or threading.Event()
        with self.lock:
            row = self.store.get(identity)
            if row is None or row["status"] != "queued" or self.closing:
                # Cancelled while queued, or left queued for the next start-up.
                self.cancels.pop(identity, None)
                return
            if cancel.is_set():
                self._finish(identity, status="cancelled")
                return
            self.store.update(identity, status="running")
        try:
            run_model_spec = model_spec_for_run(config)
            if config.mode == "pythia":
                from ..analyses.collision import analyze
                from ..readers.delphes import read
                from ..sim.pipeline import run_chain

                self._phase(identity, "Generating PYTHIA8 / DELPHES collisions")
                output = self.root / (identity + "-simulation")
                if (output / "run.json").is_file():
                    destination = output  # committed before an interrupted analysis; reuse it
                else:
                    if output.exists():
                        output.rename(
                            output.with_name(f".interrupted-{output.name}-{time.time_ns()}")
                        )
                    destination = run_chain(
                        output=output,
                        events=config.events,
                        seed=config.seed,
                        cancel=cancel,
                    )
                result = json.loads((destination / "run.json").read_text(encoding="utf8"))
                result["mode"] = "pythia"
                result["model_spec"] = run_model_spec

                def progress(completed):
                    self._phase(identity, "Analyzing reconstructed events")
                    self._progress(identity, completed, config.events)

                result["analysis"] = analyze(
                    read(destination / "events.root", include_truth=False),
                    config,
                    progress=progress,
                )
                result["output_directory"] = str(destination)
                preview = json.loads((destination / "preview.json").read_text(encoding="utf8"))
                result.update(
                    muon_display(
                        preview["muons"],
                        preview["event"],
                        model_ids=[component["id"] for component in run_model_spec["components"]],
                    )
                )
                result["event_info"] = result["analysis"]["event_rows"][0]
            else:
                count = config.events if config.source_model == "angular_sample" else 1
                analysis: dict[str, Any] = {
                    "events": count,
                    "particles": count * 2,
                    "samples": [],
                    "pairs": [],
                    "scope": (
                        "unweighted declared muon sample; not collision data or CMS calibration"
                    ),
                }
                with tempfile.TemporaryDirectory(prefix=".bench-", dir=self.root) as temporary:
                    directory = Path(temporary) / "events"
                    directory.mkdir()
                    for index in range(count):
                        event = bench(config, cancel, index)
                        observables = analyze_events([event])
                        analysis["samples"].extend(observables["samples"])
                        analysis["pairs"].extend(observables["pairs"])
                        if index == 0:
                            result = event
                        if count > 1:
                            publish(directory / f"{index}.json", event)
                        self._progress(identity, index + 1, count)
                    if cancel.is_set():
                        raise RuntimeError("run cancelled")
                    if count > 1:
                        directory.replace(self.root / f"{identity}-events")
                result.update(events=count, analysis=analysis)
            result["config"] = config.model_dump()
            result["model_spec"] = run_model_spec
            digest_payload = {
                key: item
                for key, item in result.items()
                if key not in {"artifact", "output_directory"}
            }
            result_digest = config_hash(digest_payload)
            previous_artifact = (
                result.get("artifact") if isinstance(result.get("artifact"), dict) else {}
            )
            result["artifact"] = {
                **previous_artifact,
                "format": "heplab-workbench-result-v2",
                "schema": "heplab-run-artifact-v1",
                "scope": "full_run",
                "run_id": identity,
                "parent_run_sha256": None,
                "result_sha256": result_digest,
                "model_ids": [item["id"] for item in result["model_spec"]["components"]],
                "heplab_version": __version__,
                "created_utc": datetime.now(UTC).isoformat(),
                "config_sha256": config_hash(config.model_dump()),
            }
            with self.lock:
                if cancel.is_set() and config.mode != "pythia":
                    self._finish(identity, status="queued" if self.closing else "cancelled")
                else:
                    publish(self.root / f"{identity}.json", result)
                    self._finish(identity, status="completed")
        except Exception as exc:
            with self.lock:
                if self.closing:
                    # Shutdown, not the user, stopped it: leave it for the next start-up.
                    self._finish(identity, status="queued")
                elif cancel.is_set():
                    self._finish(identity, status="cancelled", error=str(exc)[:2000])
                else:
                    self._finish(identity, status="failed", error=str(exc)[:2000])

    def close(self):
        with self.lock:
            self.closing = True
            for cancel in self.cancels.values():
                cancel.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            self.store.close()
