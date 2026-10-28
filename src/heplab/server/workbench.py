"""Local simulator jobs. Fixed operations only; no executable or path submission."""

from __future__ import annotations

import json
import math
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..io.artifacts import publish
from ..io.provenance import config_hash
from ..physics.calibration import muon_response_parameters
from ..physics.detector import geometry, silicon_stopping_power, tracker_trajectory, trajectory
from ..physics.engine import execute
from ..physics.reference import FourVector, TrackState


def muon_display(muons, event=0):
    tracks = []
    for muon in muons or []:
        eta, phi = muon["eta"], muon["phi"]
        state = TrackState(
            (0.0, 0.0, 0.0),
            FourVector.from_pt_eta_phi_mass(muon["pt"], eta, phi, 0.10565839),
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
                "points": traced["points"],
                "trajectory": traced,
            }
        )
    return {
        "event": event,
        "tracks": tracks,
        "geometry": geometry(),
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

    @model_validator(mode="after")
    def compatible_backend(self) -> Self:
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
        return self


def bench(config: RunConfig, cancel: threading.Event) -> dict:
    """Two declared back-to-back muons, not a collision event generator."""
    tracks = []
    for identity, charge in enumerate((-1, 1)):
        if cancel.is_set():
            raise RuntimeError("run cancelled")
        p = config.momentum_gev
        state = TrackState(
            (0, 0, 0), FourVector(math.hypot(p, 0.10565839), charge * p, 0, 0), charge, 0
        )
        before = (
            tracker_trajectory(state, 1.0, config.backend)
            if config.field_model == "cms_tracker"
            else trajectory(state, bz=config.bz_tesla, max_path=1.0, backend=config.backend)
        )
        stopping_power, material_reference = silicon_stopping_power(
            state.momentum.energy - 0.10565839
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
            "event_key": "bench-0",
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
            parameters = muon_response_parameters(p, 0.0)
            sampled = execute(
                {
                    "op": "simulate",
                    "particles": [{"object_id": identity, "state": asdict(state)}],
                    "config": {
                        "seed": config.seed,
                        "event_key": "bench-0",
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
        "event": 0,
        "events": 1,
        "source": "declared back-to-back muon test fixture",
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


class Jobs:
    def __init__(self, root: Path):
        self.root = root
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="heplab-simulator")
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}
        self.cancels: dict[str, threading.Event] = {}
        self.keys: dict[str, tuple[str, str]] = {}

    def submit(self, config: RunConfig, idempotency_key: str | None = None) -> str:
        fingerprint = config_hash(config.model_dump())
        with self.lock:
            if idempotency_key is not None:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", idempotency_key):
                    raise ValueError("invalid idempotency key")
                if idempotency_key in self.keys:
                    prior_hash, prior_id = self.keys[idempotency_key]
                    if prior_hash != fingerprint:
                        raise ValueError("idempotency key already belongs to different parameters")
                    return prior_id
            if len(self.jobs) >= 64:
                raise ValueError("session job budget exhausted; restart the local server")
            if any(j["status"] in {"queued", "running"} for j in self.jobs.values()):
                raise ValueError("a simulation is already active")
            identity = secrets.token_hex(12)
            self.jobs[identity] = {
                "id": identity,
                "status": "queued",
                "config": config.model_dump(),
            }
            self.cancels[identity] = threading.Event()
            if idempotency_key is not None:
                self.keys[idempotency_key] = (fingerprint, identity)
        self.pool.submit(self._run, identity, config)
        return identity

    def get(self, identity):
        with self.lock:
            return json.loads(json.dumps(self.jobs[identity]))

    def cancel(self, identity):
        with self.lock:
            self.cancels[identity].set()

    def event(self, identity, index):
        job = self.get(identity)
        if job["status"] != "completed" or not 0 <= index < 1000:
            raise ValueError("event unavailable")
        result = job["result"]
        if result["mode"] == "analytic":
            if index != 0:
                raise ValueError("bench has one event")
            return result
        if index >= result["summary"]["events"]:
            raise ValueError("event outside generated range")
        from ..readers.delphes import read

        native = next(
            read(
                self.root / (identity + "-simulation") / "events.root",
                entry_start=index,
                entry_stop=index + 1,
            )
        )
        return {**result, **muon_display(native["Muon"], index)}

    def _run(self, identity, config):
        with self.lock:
            self.jobs[identity]["status"] = "running"
        cancel = self.cancels[identity]
        try:
            if config.mode == "pythia":
                from ..sim.pipeline import run_chain

                destination = run_chain(
                    output=self.root / (identity + "-simulation"),
                    events=config.events,
                    seed=config.seed,
                    cancel=cancel,
                )
                result = json.loads((destination / "run.json").read_text(encoding="utf8"))
                result["mode"] = "pythia"
                preview = json.loads((destination / "preview.json").read_text(encoding="utf8"))
                result.update(muon_display(preview["muons"], preview["event"]))
            else:
                result = bench(config, cancel)
            with self.lock:
                if cancel.is_set() and config.mode != "pythia":
                    self.jobs[identity]["status"] = "cancelled"
                else:
                    publish(self.root / f"{identity}.json", result)
                    self.jobs[identity].update(status="completed", result=result)
        except Exception as exc:
            with self.lock:
                self.jobs[identity].update(
                    status="cancelled" if cancel.is_set() else "failed", error=str(exc)[:2000]
                )

    def close(self):
        with self.lock:
            for cancel in self.cancels.values():
                cancel.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
