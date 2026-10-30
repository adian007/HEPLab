"""Public numerical engine API with explicit reference/native backend selection."""

from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
from functools import lru_cache

from .constants import MUON_MASS_GEV
from .reference import (
    FourVector,
    TrackState,
    WeightedHistogram,
    addressed_normal,
    addressed_uniform,
    propagate_uniform_bz,
)


@lru_cache(maxsize=1)
def _rust_binding() -> tuple[bool, str | None]:
    try:
        import heplab_kernels

        if not callable(getattr(heplab_kernels, "run_json", None)):
            return False, "Native Rust binding is incompatible: run_json is missing"
        result = json.loads(
            heplab_kernels.run_json(
                json.dumps(
                    {
                        "op": "mass",
                        "first": [45, 0, 0, MUON_MASS_GEV],
                        "second": [45, 0, math.pi, MUON_MASS_GEV],
                    }
                )
            )
        )
        if not isinstance(result, int | float) or not math.isclose(
            result, 2 * math.hypot(45.0, MUON_MASS_GEV), abs_tol=1e-6
        ):
            return False, "Native Rust binding failed its startup numerical check"
        return True, None
    except (ImportError, OSError, ValueError) as exc:
        return False, f"Native Rust binding unavailable: {exc}"


def capabilities() -> dict:
    rust, error = _rust_binding()
    return {
        "reference": True,
        "rust_extension": rust,
        "rust_error": error,
        "rust_executable_configured": bool(os.environ.get("HEPLAB_RUST_EXECUTABLE")),
        "fidelity": "T0-analytic-thin-slab-and-educational-response",
        "calibrated_detector": False,
        "material_transport": "bounded_thin_slab",
        "digitization": "deposit_threshold_noise_saturation",
        "geometry_navigation": "finite_cylinders_and_annular_disks",
        "field_models": ["ideal_bore", "cms_tracker_oae_3_8t"],
        "full_cms_material_map": False,
    }


def _state(value):
    return TrackState(
        tuple(value["position"]), FourVector(**value["momentum"]), value["charge"], value["time_ns"]
    )


def _serialize(state):
    from dataclasses import asdict

    return asdict(state)


def trajectory_reference(request: dict) -> dict:
    """Pure-Python composite trajectory; the oracle for the Rust kernel op."""
    from .detector import surface_paths

    state = _state(request["state"])
    bz, max_path, step = request["bz_tesla"], request["max_path_m"], request["step_m"]
    exits = [p for s in request["exit_surfaces"] for p in surface_paths(state, s, bz, max_path)]
    exit_path = min(exits, default=max_path)
    boundary = propagate_uniform_bz(state, exit_path, bz)

    def at(path):
        return (
            propagate_uniform_bz(state, path, bz)
            if path <= exit_path
            else propagate_uniform_bz(boundary, path - exit_path, 0.0)
        )

    crossings = []
    for surface in request["surfaces"]:
        for path in surface_paths(state, surface, bz, exit_path):
            moved = at(path)
            crossings.append(
                {
                    "surface_id": surface["id"],
                    "path_m": path,
                    "position_m": list(moved.position),
                    "time_ns": moved.time_ns,
                    "kind": "predicted_surface_crossing",
                }
            )
    paths = sorted(
        {
            0.0,
            max_path,
            exit_path,
            *(min(i * step, max_path) for i in range(math.ceil(max_path / step) + 1)),
            *(crossing["path_m"] for crossing in crossings),
        }
    )
    return {
        "points": [list(at(s).position) for s in paths],
        "path_m": paths,
        "crossings": sorted(crossings, key=lambda c: c["path_m"]),
        "field_exit_path_m": exit_path if exits else None,
        "termination": "path_budget_after_field_exit" if exits else "path_budget_inside_field",
    }


def _reference(request):
    op = request["op"]
    if op == "cms_tracker_field":
        from .cms_field import tracker_field

        return tracker_field(request["position_m"])
    if op == "trace_cms_tracker":
        from .cms_field import trace_tracker

        return trace_tracker(_state(request["state"]), request["path_length_m"], request["step_m"])
    if op == "trajectory":
        return trajectory_reference(request)
    if op == "intersect":
        from .detector import surface_paths

        return surface_paths(
            _state(request["state"]), request["surface"], request["bz_tesla"], request["max_path_m"]
        )
    if op == "material":
        from .material import interact

        return interact(_state(request["state"]), request["slab"], request["address"])
    if op == "digitize":
        from .material import digitize

        return digitize(request["deposit_gev"], request["config"], request["address"])
    if op == "mass":
        return (
            FourVector.from_pt_eta_phi_mass(*request["first"])
            + FourVector.from_pt_eta_phi_mass(*request["second"])
        ).physical_mass
    if op == "boost":
        from dataclasses import asdict

        return asdict(FourVector(**request["vector"]).boost(tuple(request["beta"])))
    if op == "propagate":
        return _serialize(
            propagate_uniform_bz(
                _state(request["state"]), request["path_length_m"], request["bz_tesla"]
            )
        )
    if op in {"uniform", "normal"}:
        function = addressed_uniform if op == "uniform" else addressed_normal
        return function(**request["address"])
    if op == "histogram":
        histogram = WeightedHistogram(tuple(request["edges"]))
        for x, w in request["fills"]:
            histogram.fill(x, w)
        return histogram.snapshot()
    if op == "simulate":
        cfg = request["config"]
        efficiency = cfg["efficiency"]
        resolution = cfg["relative_pt_resolution"]
        momentum_scale = cfg.get("momentum_scale", 1.0)
        if (
            not math.isfinite(efficiency)
            or not 0 <= efficiency <= 1
            or not math.isfinite(resolution)
            or resolution < 0
            or not math.isfinite(momentum_scale)
            or momentum_scale <= 0
            or type(cfg["max_objects"]) is not int
            or cfg["max_objects"] <= 0
            or len(request["particles"]) > cfg["max_objects"]
        ):
            raise ValueError("invalid response parameters/budgets")
        objects = []
        ids = set()
        for particle in request["particles"]:
            identity = particle["object_id"]
            if identity in ids:
                raise ValueError("duplicate object identity")
            ids.add(identity)
            state = propagate_uniform_bz(
                _state(particle["state"]), cfg["path_length_m"], cfg["bz_tesla"]
            )
            address = {
                "master_seed": cfg["seed"],
                "event_key": cfg["event_key"],
                "object_id": identity,
                "model_id": "educational-response-v1",
                "correlation_group": "nominal",
            }
            if addressed_uniform(**address, stage_id="tracking_efficiency") >= efficiency:
                continue
            sigma = math.sqrt(2 * math.log(math.hypot(resolution, 1)))
            scale = momentum_scale * math.exp(
                sigma * addressed_normal(**address, stage_id="momentum_resolution")
                - 0.5 * sigma * sigma
            )
            p4 = state.momentum
            moved = FourVector(
                math.hypot(p4.momentum * scale, p4.physical_mass),
                p4.px * scale,
                p4.py * scale,
                p4.pz * scale,
            )
            objects.append(
                {
                    "object_id": identity,
                    "state": _serialize(
                        TrackState(state.position, moved, state.charge, state.time_ns)
                    ),
                }
            )
        return {
            "fidelity": "T0",
            "validation": "educational_unvalidated",
            "model": "educational-response-v1",
            "objects": objects,
            "input_objects": len(request["particles"]),
            "accepted_objects": len(objects),
        }
    raise ValueError(f"unsupported engine operation {op!r}")


def execute(request: dict, *, backend="reference"):
    required = {
        "intersect": {"op", "state", "surface", "bz_tesla", "max_path_m"},
        "material": {"op", "state", "slab", "address"},
        "digitize": {"op", "deposit_gev", "config", "address"},
        "cms_tracker_field": {"op", "position_m"},
        "trace_cms_tracker": {"op", "state", "path_length_m", "step_m"},
        "trajectory": {
            "op",
            "state",
            "surfaces",
            "exit_surfaces",
            "bz_tesla",
            "max_path_m",
            "step_m",
        },
        "mass": {"op", "first", "second"},
        "boost": {"op", "vector", "beta"},
        "propagate": {"op", "state", "path_length_m", "bz_tesla"},
        "uniform": {"op", "address"},
        "normal": {"op", "address"},
        "histogram": {"op", "edges", "fills"},
        "simulate": {"op", "particles", "config"},
    }
    if not isinstance(request, dict) or request.get("op") not in required:
        raise ValueError("unknown engine operation")
    if set(request) != required[request["op"]]:
        raise ValueError("missing or unknown engine request fields")
    if request["op"] == "cms_tracker_field":
        from .cms_field import tracker_field

        tracker_field(request["position_m"])  # identical domain/type checks for both backends
    if request["op"] == "trace_cms_tracker":
        state = request["state"]
        if (
            not isinstance(state, dict)
            or set(state) != {"position", "momentum", "charge", "time_ns"}
            or not isinstance(state["momentum"], dict)
            or set(state["momentum"]) != {"energy", "px", "py", "pz"}
        ):
            raise ValueError("missing or unknown tracker state fields")
        from .cms_field import tracker_field

        tracker_field(state["position"])
        numbers = [
            request["path_length_m"],
            request["step_m"],
            state["charge"],
            state["time_ns"],
            *state["momentum"].values(),
        ]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
            raise ValueError("tracker fields require finite numbers, not booleans")
    if request["op"] == "trajectory":
        state = request["state"]
        if (
            not isinstance(state, dict)
            or set(state) != {"position", "momentum", "charge", "time_ns"}
            or not isinstance(state["momentum"], dict)
            or set(state["momentum"]) != {"energy", "px", "py", "pz"}
            or not isinstance(state["position"], list | tuple)
            or len(state["position"]) != 3
        ):
            raise ValueError("missing or unknown trajectory state fields")
        if (
            not isinstance(request["surfaces"], list)
            or not request["surfaces"]
            or not isinstance(request["exit_surfaces"], list)
            or not request["exit_surfaces"]
        ):
            raise ValueError("trajectory requires nonempty surface lists")
        surface_fields = {
            "cylinder": {"id", "kind", "radius_m", "half_length_m"},
            "disk": {"id", "kind", "z_m", "inner_radius_m", "outer_radius_m"},
        }
        for surface in [*request["surfaces"], *request["exit_surfaces"]]:
            if (
                not isinstance(surface, dict)
                or surface.get("kind") not in surface_fields
                or set(surface) != surface_fields[surface["kind"]]
                or not isinstance(surface["id"], str)
            ):
                raise ValueError("missing or unknown trajectory surface fields")
            dimensions = [v for k, v in surface.items() if k not in {"id", "kind"}]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in dimensions):
                raise ValueError("trajectory surface dimensions must be finite numbers")
            if surface["kind"] == "cylinder":
                valid = surface["radius_m"] > 0 and surface["half_length_m"] > 0
            else:
                valid = 0 <= surface["inner_radius_m"] < surface["outer_radius_m"]
            if not valid:
                raise ValueError("invalid trajectory surface dimensions")
        numbers = [
            request["bz_tesla"],
            request["max_path_m"],
            request["step_m"],
            state["charge"],
            state["time_ns"],
            *state["position"],
            *state["momentum"].values(),
        ]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
            raise ValueError("trajectory fields require finite numbers, not booleans")
        if not 0.005 <= request["step_m"] <= 0.2 or not 0 < request["max_path_m"] <= 20:
            raise ValueError("trajectory sampling/path budget invalid")
        x, y, z = state["position"]
        if math.hypot(x, y) >= 3.0 or abs(z) >= 6.25:
            raise ValueError("trajectory must start inside the modeled solenoid bore")
    if request["op"] == "intersect":
        surface = request["surface"]
        surface_fields = {
            "cylinder": {"kind", "radius_m", "half_length_m"},
            "disk": {"kind", "z_m", "inner_radius_m", "outer_radius_m"},
        }
        if (
            not isinstance(surface, dict)
            or surface.get("kind") not in surface_fields
            or set(surface) != surface_fields[surface["kind"]]
        ):
            raise ValueError("missing or unknown surface fields")
        state = request["state"]
        if not isinstance(state, dict) or set(state) != {
            "position",
            "momentum",
            "charge",
            "time_ns",
        }:
            raise ValueError("missing or unknown track state fields")
        if not isinstance(state["momentum"], dict) or set(state["momentum"]) != {
            "energy",
            "px",
            "py",
            "pz",
        }:
            raise ValueError("missing or unknown momentum fields")
        position = state["position"]
        if not isinstance(position, list | tuple) or len(position) != 3:
            raise ValueError("position must have three components")
        numbers = [v for k, v in surface.items() if k != "kind"]
        numbers += [
            request["bz_tesla"],
            request["max_path_m"],
            state["charge"],
            state["time_ns"],
            *position,
            *state["momentum"].values(),
        ]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
            raise ValueError("intersection fields require finite numbers, not booleans")
    if request["op"] in {"material", "digitize"}:
        address_fields = {
            "master_seed",
            "event_key",
            "object_id",
            "stage_id",
            "counter",
            "correlation_group",
            "model_id",
        }
        if not isinstance(request["address"], dict) or set(request["address"]) != address_fields:
            raise ValueError("missing or unknown random address fields")
        addressed_uniform(**request["address"])
        if request["op"] == "material":
            state = request["state"]
            if set(state) != {"position", "momentum", "charge", "time_ns"} or set(
                state["momentum"]
            ) != {"energy", "px", "py", "pz"}:
                raise ValueError("missing or unknown track state fields")
    serialized = json.dumps(request, sort_keys=True, allow_nan=False)
    if len(serialized.encode("utf8")) > 1_048_576:
        raise ValueError("engine request exceeds 1 MiB")
    if backend == "reference":
        return _reference(request)
    if backend != "rust":
        raise ValueError("backend must be reference or rust")
    if importlib.util.find_spec("heplab_kernels") is not None:
        import heplab_kernels

        return json.loads(heplab_kernels.run_json(serialized))
    executable = os.environ.get("HEPLAB_RUST_EXECUTABLE")
    if not executable:
        raise RuntimeError(
            "Rust backend unavailable: install the kernels wheel "
            "or configure HEPLAB_RUST_EXECUTABLE"
        )
    command = [executable]
    if os.environ.get("HEPLAB_RUST_WSL_DISTRO"):
        command = ["wsl.exe", "-d", os.environ["HEPLAB_RUST_WSL_DISTRO"], "--", executable]
    result = subprocess.run(
        command,
        input=serialized + "\n",
        capture_output=True,
        text=True,
        encoding="utf8",
        timeout=30,
        check=True,
    )
    if len(result.stdout) > 4_194_304:
        raise RuntimeError("Rust backend output exceeds its budget")
    response = json.loads(result.stdout)
    if not response["ok"]:
        raise ValueError(response["error"])
    return response["result"]
