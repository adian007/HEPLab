"""Sourced surface geometry and analytic helix navigation in SI/GeV units.

Surfaces predict crossings; they are not sensor hits or a full CMS material map.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

from ..io.provenance import config_hash
from .constants import CURVATURE_GEV_T_METRES, SPEED_OF_LIGHT_M_PER_NS
from .reference import TrackState, propagate_uniform_bz


def tracker_trajectory(state: TrackState, max_path: float, backend: str = "reference") -> dict:
    """CMS tracker OAE field; 5 mm RK4 steps, no extrapolation beyond validity.

    Crossings are intersections of the sampled polyline with the guide surfaces.
    They are display predictions, not sensor hits or precision navigation.
    """
    from .engine import execute
    from .reference import FourVector

    traced = execute(
        {
            "op": "trace_cms_tracker",
            "state": asdict(state),
            "path_length_m": max_path,
            "step_m": 0.005,
        },
        backend=backend,
    )
    crossings = []
    # Build (and hash) the surface model once, not once per 5 mm segment.
    surfaces = geometry()["surfaces"]
    for index in range(1, len(traced["points"])):
        a, b = traced["points"][index - 1 : index + 1]
        delta = [b[i] - a[i] for i in range(3)]
        chord = math.hypot(*delta)
        if chord < 1e-12:
            continue
        direction = [v / chord for v in delta]
        segment = TrackState(tuple(a), FourVector(1, *direction), 0, 0)
        for surface in surfaces:
            for distance in surface_paths(segment, surface, 0, chord):
                path = traced["path_m"][index - 1] + distance / chord * (
                    traced["path_m"][index] - traced["path_m"][index - 1]
                )
                crossings.append(
                    {
                        "surface_id": surface["id"],
                        "path_m": path,
                        "position_m": [a[i] + distance * direction[i] for i in range(3)],
                        "time_ns": state.time_ns
                        + path
                        * state.momentum.energy
                        / (state.momentum.momentum * SPEED_OF_LIGHT_M_PER_NS),
                    }
                )
    crossings.sort(key=lambda item: item["path_m"])
    return {
        **traced,
        "crossings": crossings,
        "crossing_method": "5 mm sampled-polyline intersections; display only",
        "field_exit_path_m": traced["actual_path_m"]
        if traced["termination"] == "field_validity_boundary"
        else None,
        "navigation_backend": backend,
        "geometry_sha256": geometry("cms_tracker")["sha256"],
    }


def geometry(field_model: str = "ideal_bore") -> dict:
    if field_model not in {"ideal_bore", "cms_tracker"}:
        raise ValueError("unknown detector field model")
    pixel_source = "https://cds.cern.ch/record/1971152/files/CR2014_389.pdf"
    surfaces = [
        {
            "id": f"BPIX{i + 1}",
            "kind": "cylinder",
            "radius_m": r,
            "half_length_m": 0.265,
            "subsystem": "pixel",
            "source": pixel_source,
        }
        for i, r in enumerate((0.044, 0.073, 0.102))
    ]
    for sign in (-1, 1):
        for index, z in enumerate((0.345, 0.465), 1):
            surfaces.append(
                {
                    "id": f"FPIX{'M' if sign < 0 else 'P'}{index}",
                    "kind": "disk",
                    "z_m": sign * z,
                    "inner_radius_m": 0.06,
                    "outer_radius_m": 0.15,
                    "subsystem": "pixel",
                    "source": pixel_source,
                }
            )
    # Envelopes have sourced extents, not invented internal sensor positions.
    surfaces.extend(
        [
            {
                "id": "strip-envelope",
                "kind": "cylinder",
                "radius_m": 1.10,
                "half_length_m": 2.80,
                "subsystem": "tracker-envelope",
                "source": "https://cds.cern.ch/record/1277738/files/fermilab-pub-10-724-cms.pdf",
            },
            {
                "id": "solenoid-bore",
                "kind": "cylinder",
                "radius_m": 3.0,
                "half_length_m": 6.25,
                "subsystem": "solenoid",
                "source": "https://cms.cern/news/pay-attention-cms-magnet-powered",
            },
        ]
    )
    value = {
        "id": "cms-original-tracker-surfaces-v1",
        "era": "original pixel detector, 2009–2016",
        "units": "metres",
        "surfaces": surfaces,
        "field": {"model": "ideal uniform solenoid; zero outside bore", "nominal_bz_t": 3.8},
        "limits": [
            "surface/envelope model; no module layout or services",
            "no measured hit or full CMS field/material-map claim",
        ],
    }
    if field_model == "cms_tracker":
        from .cms_field import MODEL, SOURCE

        value["field"] = {
            "model": MODEL,
            "nominal_bz_t": 3.8,
            "source": SOURCE,
            "validity": "r<1.15 m and |z|<2.8 m; stop outside",
        }
    value["sha256"] = config_hash(value)
    return value


def surface_paths(state: TrackState, surface: dict, bz: float, max_path: float) -> list[float]:
    """All forward intersections, including tangencies and repeated helix turns.

    On-surface roots at zero are excluded; no spatial nudge skips a thin layer.
    """
    if not math.isfinite(max_path) or not 0 < max_path <= 100:
        raise ValueError("path budget must be in (0,100] m")
    p4 = state.momentum
    p = p4.momentum
    if p <= 0 or not math.isfinite(bz):
        raise ValueError("invalid moving track or field")
    x, y, z = state.position
    ux, uy, uz = p4.px / p, p4.py / p, p4.pz / p
    tolerance = 1e-9
    if surface["kind"] == "disk":
        low, high, target = (surface[k] for k in ("inner_radius_m", "outer_radius_m", "z_m"))
        if not all(math.isfinite(v) for v in (low, high, target)) or not 0 <= low < high:
            raise ValueError("invalid annular disk")
        if abs(uz) < 1e-15:
            return []  # coplanar motion is not a discrete crossing
        path = (target - z) / uz
        if not tolerance < path <= max_path:
            return []
        point = propagate_uniform_bz(state, path, bz).position
        return [path] if low - tolerance <= math.hypot(*point[:2]) <= high + tolerance else []
    if surface["kind"] != "cylinder":
        raise ValueError("unsupported surface")
    radius, half = surface["radius_m"], surface["half_length_m"]
    if not all(math.isfinite(v) and v > 0 for v in (radius, half)):
        raise ValueError("invalid finite cylinder")
    omega = -CURVATURE_GEV_T_METRES * state.charge * bz / p
    candidates = []
    if abs(omega) * max_path < 1e-8:
        a, b, c = ux * ux + uy * uy, 2 * (x * ux + y * uy), x * x + y * y - radius * radius
        if a < 1e-30:
            return []
        discriminant = b * b - 4 * a * c
        if discriminant < -1e-13 * max(1, b * b, abs(4 * a * c)):
            return []
        root = math.sqrt(max(0, discriminant))
        # Stable quadratic roots avoid cancellation for near-boundary origins.
        q = -0.5 * (b + math.copysign(root, b))
        candidates = [q / a, c / q] if q else [-b / (2 * a)]
    else:
        cx, cy = x - uy / omega, y + ux / omega
        distance, track_radius = math.hypot(cx, cy), math.hypot(ux, uy) / abs(omega)
        if distance < 1e-14 or track_radius == 0:
            return []  # concentric coincident circles have no isolated crossings
        along = (radius * radius - track_radius * track_radius + distance * distance) / (
            2 * distance
        )
        height2 = radius * radius - along * along
        if height2 < -1e-12 * max(1, radius * radius):
            return []
        height = math.sqrt(max(0, height2))
        vx, vy = x - cx, y - cy
        turn_count = abs(omega) * max_path / math.tau
        if not math.isfinite(turn_count) or turn_count > 1023:
            raise ValueError("helix turn budget exceeded")
        turns = math.ceil(turn_count) + 1
        if turns > 1024:
            raise ValueError("helix turn budget exceeded")
        for sign in (-1, 1):
            ix, iy = (
                along * cx / distance - sign * height * cy / distance,
                along * cy / distance + sign * height * cx / distance,
            )
            dx, dy = ix - cx, iy - cy
            angle = math.atan2(vx * dy - vy * dx, vx * dx + vy * dy)
            candidates.extend((angle + math.tau * n) / omega for n in range(-turns, turns + 1))
    output: list[float] = []
    for path in sorted(candidates):
        if tolerance < path <= max_path and abs(z + uz * path) <= half + tolerance:
            if not output or abs(path - output[-1]) > tolerance:
                output.append(path)
    return output


def _surface_request(surface: dict) -> dict:
    fields = (
        ("radius_m", "half_length_m")
        if surface["kind"] == "cylinder"
        else ("z_m", "inner_radius_m", "outer_radius_m")
    )
    return {"id": surface["id"], "kind": surface["kind"], **{k: surface[k] for k in fields}}


def trajectory(state: TrackState, *, bz=3.8, max_path=16.0, step=0.05, backend="reference") -> dict:
    """Helix inside ideal solenoid, straight outside; explicitly no return field."""
    if not math.isfinite(step) or not 0.005 <= step <= 0.2 or not 0 < max_path <= 20:
        raise ValueError("trajectory sampling/path budget invalid")
    if math.hypot(*state.position[:2]) >= 3.0 or abs(state.position[2]) >= 6.25:
        raise ValueError("trajectory must start inside the modeled solenoid bore")
    detector = geometry()

    if backend == "rust":
        # One composite call: sampling, field exit and crossings in the kernel,
        # instead of separate per-surface intersection calls.
        from .engine import execute

        bore = detector["surfaces"][-1]
        faces = [
            {
                "id": f"bore-end-{'m' if sign < 0 else 'p'}",
                "kind": "disk",
                "z_m": sign * 6.25,
                "inner_radius_m": 0.0,
                "outer_radius_m": 3.0,
            }
            for sign in (-1, 1)
        ]
        payload = execute(
            {
                "op": "trajectory",
                "state": asdict(state),
                "surfaces": [_surface_request(s) for s in detector["surfaces"]],
                "exit_surfaces": [_surface_request(s) for s in [bore, *faces]],
                "bz_tesla": bz,
                "max_path_m": max_path,
                "step_m": step,
            },
            backend="rust",
        )
        return {
            **payload,
            "field_bz_tesla": bz,
            "geometry_sha256": detector["sha256"],
            "model": "ideal-solenoid-helix-v1",
            "validation": "analytic_model_only",
            "navigation_backend": backend,
        }
    if backend != "reference":
        raise ValueError("trajectory backend must be reference or rust")

    def intersections(surface, limit):
        return surface_paths(state, surface, bz, limit)

    bore = detector["surfaces"][-1]
    # Add both bore end faces for field exit navigation.
    faces = [
        {
            "id": "bore-end",
            "kind": "disk",
            "z_m": sign * 6.25,
            "inner_radius_m": 0.0,
            "outer_radius_m": 3.0,
        }
        for sign in (-1, 1)
    ]
    exits = [s for surface in [bore, *faces] for s in intersections(surface, max_path)]
    exit_path = min(exits, default=max_path)
    boundary = propagate_uniform_bz(state, exit_path, bz)

    def at(path):
        return (
            propagate_uniform_bz(state, path, bz)
            if path <= exit_path
            else propagate_uniform_bz(boundary, path - exit_path, 0.0)
        )

    crossings = []
    for surface in detector["surfaces"]:
        for path in intersections(surface, exit_path):
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
        "field_bz_tesla": bz,
        "termination": "path_budget_after_field_exit" if exits else "path_budget_inside_field",
        "geometry_sha256": detector["sha256"],
        "model": "ideal-solenoid-helix-v1",
        "validation": "analytic_model_only",
        "navigation_backend": backend,
    }


def silicon_stopping_power(kinetic_gev: float) -> tuple[float, dict]:
    from .calibration import REFERENCE, interpolate

    payload = json.loads((REFERENCE / "silicon-calibration.json").read_text())
    if config_hash({k: v for k, v in payload.items() if k != "sha256"}) != payload.get("sha256"):
        raise ValueError("material calibration checksum mismatch")
    if payload["status"] != "reference_calibrated":
        raise ValueError("material reference validation did not pass")
    return interpolate(payload["knots"], kinetic_gev), {
        "id": payload["id"],
        "source_sha256": payload["source_sha256"],
        "scope": payload["scope"],
        "kinetic_gev": kinetic_gev,
        "heldout_max_relative_error": payload["max_abs_relative_error"],
    }
