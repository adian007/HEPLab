"""CMS OAE tracker field, ported from CMSSW_10_6_30 BCyl.h/TkBfield.cc.

V. Karimaki's off-axis expansion of TOSCA 1103l, tuned on MTCC field
measurements (2006). This is a fixed nominal 3.8 T parametrization, not an
IOV-resolved Run2016 conditions map. Source: cms-sw/cmssw commit
c04fa510bb587b8ee3fa171888468f80de714fa8, Apache-2.0.
"""

from __future__ import annotations

import math
from dataclasses import asdict

from .constants import CURVATURE_GEV_T_METRES, SPEED_OF_LIGHT_M_PER_NS
from .reference import FourVector, TrackState

MODEL = "cms-oae-1103l-3.8T-tracker-v1"
SOURCE = (
    "https://github.com/cms-sw/cmssw/blob/"
    "c04fa510bb587b8ee3fa171888468f80de714fa8/"
    "MagneticField/ParametrizedEngine/src/BCyl.h"
)


def tracker_field(position) -> list[float]:
    if (
        not isinstance(position, list | tuple)
        or len(position) != 3
        or any(type(x) not in (float, int) or not math.isfinite(x) for x in position)
    ):
        raise ValueError("field position requires three finite numbers")
    x, y, z = position
    r2 = x * x + y * y
    if r2 >= 1.15**2 or abs(z) >= 2.8:
        raise ValueError("CMS OAE field is only defined at r<1.15 m and |z|<2.8 m")
    parameters = (
        4.24326,
        15.0201,
        3.81492,
        0.0178712,
        0.000656527,
        2.45818,
        0.00778695,
        2.125,
        1.77436,
    )
    a, length, nominal, shift, radial, radial_z, gaussian, mean, width = parameters
    ap2 = 4 * a * a / (length * length)
    half_b = 0.5 * nominal * math.sqrt(1 + ap2)
    hlova = 1 / math.sqrt(ap2)
    inverse_a = 2 * hlova / length
    z -= shift

    def derivatives(u):
        base = 1 / (1 + u * u)
        root = math.sqrt(base)
        return (
            u * root,
            base * root,
            -3 * base * base * u * root,
            -3 * base**3 * root * (1 - 4 * u * u),
        )

    fu, gv = derivatives(hlova - z * inverse_a), derivatives(hlova + z * inverse_a)
    rat = 0.5 * inverse_a
    rat2 = rat * rat * r2
    br = half_b * rat * (fu[1] - gv[1] - (fu[3] - gv[3]) * rat2 * 0.5)
    bz = half_b * (fu[0] + gv[0] - (fu[2] + gv[2]) * rat2)
    br += radial * z * (abs(z) - radial_z) ** 2
    bz -= gaussian * (
        math.exp(-((z - mean) ** 2) / width**2) + math.exp(-((z + mean) ** 2) / width**2)
    )
    return [br * x, br * y, bz]


def trace_tracker(state: TrackState, path_length_m: float, step_m: float) -> dict:
    """Vacuum RK4 reference; stop at the field validity edge within 0.1 micrometre."""
    tracker_field(list(state.position))
    _ = state.momentum.physical_mass
    p = state.momentum.momentum
    numbers = [path_length_m, step_m, state.charge, state.time_ns]
    if (
        any(type(v) not in (float, int) or not math.isfinite(v) for v in numbers)
        or not 0 <= path_length_m <= 20
        or not 0.001 <= step_m <= 0.01
        or p < 0.1
        or abs(state.charge) > 1
        or state.time_ns < 0
    ):
        raise ValueError("invalid tracker transport domain/budget")
    y = [*state.position, state.momentum.px, state.momentum.py, state.momentum.pz]
    points, paths = [list(state.position)], [0.0]
    path, maximum, stopped = 0.0, 0.0, False

    def derivative(values):
        b = tracker_field(values[:3])
        magnitude = math.hypot(*values[3:])
        u = [v / magnitude for v in values[3:]]
        k = CURVATURE_GEV_T_METRES * state.charge
        return [
            *u,
            k * (u[1] * b[2] - u[2] * b[1]),
            k * (u[2] * b[0] - u[0] * b[2]),
            k * (u[0] * b[1] - u[1] * b[0]),
        ]

    for _ in range(20_100):
        remaining = path_length_m - path
        if remaining <= 1e-12:
            break
        h = min(step_m, remaining, 0.05 * p / (CURVATURE_GEV_T_METRES * 4))
        while True:
            try:
                k1 = derivative(y)
                k2 = derivative([v + h * 0.5 * k for v, k in zip(y, k1, strict=True)])
                k3 = derivative([v + h * 0.5 * k for v, k in zip(y, k2, strict=True)])
                k4 = derivative([v + h * k for v, k in zip(y, k3, strict=True)])
                next_y = [y[i] + h * (k1[i] + 2 * k2[i] + 2 * k3[i] + k4[i]) / 6 for i in range(6)]
                tracker_field(next_y[:3])
                break
            except ValueError:
                if h <= 1e-7:
                    stopped = True
                    break
                h *= 0.5
        if stopped:
            break
        magnitude = math.hypot(*next_y[3:])
        drift = abs(magnitude / p - 1)
        if drift >= 1e-7:
            raise ValueError("RK4 momentum drift exceeds numerical gate")
        maximum = max(maximum, drift)
        y = next_y[:3] + [v * p / magnitude for v in next_y[3:]]
        path += h
        points.append(y[:3])
        paths.append(path)
    if not stopped and path_length_m - path > 1e-12:
        raise ValueError("tracker step budget exhausted")
    final = TrackState(
        (y[0], y[1], y[2]),
        FourVector(state.momentum.energy, *y[3:]),
        state.charge,
        state.time_ns + path * state.momentum.energy / (p * SPEED_OF_LIGHT_M_PER_NS),
    )
    return {
        "state": asdict(final),
        "points": points,
        "path_m": paths,
        "actual_path_m": path,
        "termination": "field_validity_boundary" if stopped else "path_budget",
        "max_relative_momentum_drift": maximum,
        "step_m": step_m,
        "field_model": MODEL,
    }
