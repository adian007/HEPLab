"""Bounded educational comparisons of magnetic curvature and sagitta."""

from __future__ import annotations

import bisect
import math

from .cms_field import trace_tracker
from .constants import CURVATURE_GEV_T_METRES, MUON_MASS_GEV
from .reference import FourVector, TrackState, propagate_uniform_bz

MODEL_ID = "magnetic-curvature-sweep-v1"
DEFAULT_MOMENTA_GEV_C = (1.0, 5.0, 20.0, 100.0)
DEFAULT_FIELDS_T = (0.0, 2.0, 3.8, 5.0)
DEFAULT_CHARGES_E = (-1.0, 1.0)


def _state(momentum_gev_c: float, charge_e: float) -> TrackState:
    energy = math.hypot(momentum_gev_c, MUON_MASS_GEV)
    return TrackState(
        (0.0, 0.0, 0.0),
        FourVector(energy, momentum_gev_c, 0.0, 0.0),
        charge_e,
    )


def _interpolate(points: list[list[float]], paths: list[float], path: float) -> list[float]:
    index = min(len(paths) - 2, max(0, bisect.bisect_right(paths, path) - 1))
    width = paths[index + 1] - paths[index]
    fraction = 0.0 if width == 0 else (path - paths[index]) / width
    return [a + fraction * (b - a) for a, b in zip(points[index], points[index + 1], strict=True)]


def signed_sagitta_m(start: list[float], midpoint: list[float], end: list[float]) -> float:
    """Signed transverse midpoint deviation from the endpoint chord, in metres."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("sagitta chord must have nonzero transverse length")
    deviation_x = midpoint[0] - (start[0] + end[0]) / 2
    deviation_y = midpoint[1] - (start[1] + end[1]) / 2
    return (dx * deviation_y - dy * deviation_x) / length


def curvature_sweep(
    *,
    path_length_m: float = 1.0,
    momenta_gev_c: tuple[float, ...] = DEFAULT_MOMENTA_GEV_C,
    fields_t: tuple[float, ...] = DEFAULT_FIELDS_T,
    charges_e: tuple[float, ...] = DEFAULT_CHARGES_E,
    tracker_step_m: float = 0.005,
) -> dict:
    """Compare uniform-field exact helices with the bounded OAE tracker reference.

    Uniform-field rows are analytic vacuum propagation at eta=0. Tracker rows use
    the pinned CMS OAE field function and RK4 only inside its declared field domain.
    They are software model comparisons, not measurements of the CMS field.
    """
    values = (*momenta_gev_c, *fields_t, *charges_e, path_length_m, tracker_step_m)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("curvature sweep values must be finite")
    if not 0.1 <= path_length_m <= 20:
        raise ValueError("path_length_m must be in [0.1, 20] m")
    if not 0.001 <= tracker_step_m <= 0.01:
        raise ValueError("tracker_step_m must be in [0.001, 0.01] m")
    if not momenta_gev_c or any(not 0.1 <= value <= 100 for value in momenta_gev_c):
        raise ValueError("momentum grid must be nonempty and inside [0.1, 100] GeV/c")
    if not fields_t or any(abs(value) > 8 for value in fields_t):
        raise ValueError("field grid must be nonempty and inside [-8, 8] T")
    if not charges_e or any(abs(value) != 1 for value in charges_e):
        raise ValueError("charge grid must contain singly charged muons")

    ideal_rows = []
    for momentum in momenta_gev_c:
        for field in fields_t:
            for charge in charges_e:
                state = _state(momentum, charge)
                middle = propagate_uniform_bz(state, path_length_m / 2, field)
                final = propagate_uniform_bz(state, path_length_m, field)
                sagitta = signed_sagitta_m(
                    list(state.position), list(middle.position), list(final.position)
                )
                radius = None if field == 0 else momentum / (CURVATURE_GEV_T_METRES * abs(field))
                ideal_rows.append(
                    {
                        "momentum_gev_c": momentum,
                        "field_t": field,
                        "charge_e": charge,
                        "radius_m": radius,
                        "signed_sagitta_m": sagitta,
                        "endpoint_m": list(final.position),
                        "scope": "exact uniform axial field; vacuum; eta=0; no material or decay",
                    }
                )

    tracker_rows = []
    for momentum in momenta_gev_c:
        for charge in charges_e:
            state = _state(momentum, charge)
            result = trace_tracker(state, path_length_m, tracker_step_m)
            midpoint = _interpolate(result["points"], result["path_m"], result["actual_path_m"] / 2)
            sagitta = signed_sagitta_m(
                list(state.position), midpoint, list(result["state"]["position"])
            )
            ideal = propagate_uniform_bz(state, path_length_m, 3.8)
            tracker_rows.append(
                {
                    "momentum_gev_c": momentum,
                    "charge_e": charge,
                    "signed_sagitta_m": sagitta,
                    "endpoint_m": result["state"]["position"],
                    "actual_path_m": result["actual_path_m"],
                    "termination": result["termination"],
                    "difference_from_uniform_3_8t_endpoint_m": math.dist(
                        result["state"]["position"], ideal.position
                    ),
                    "scope": (
                        "pinned CMS tracker OAE field function + RK4; nominal 3.8 T; "
                        "field-domain limited"
                    ),
                }
            )

    return {
        "schema": "heplab-curvature-sweep-v1",
        "model_id": MODEL_ID,
        "config": {
            "path_length_m": path_length_m,
            "momenta_gev_c": list(momenta_gev_c),
            "uniform_fields_t": list(fields_t),
            "charges_e": list(charges_e),
            "tracker_step_m": tracker_step_m,
        },
        "ideal_uniform_field": ideal_rows,
        "tracker_oae_reference": tracker_rows,
        "limits": [
            "Software comparison of declared equations and one pinned OAE field function only.",
            "The OAE function is not independently validated against CMS field measurements "
            "or run-era conditions.",
            "No material transport, scattering, decay, detector response, or calibration.",
        ],
    }
