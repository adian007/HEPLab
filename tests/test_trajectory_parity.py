"""Composite trajectory op: the Rust kernel must match the Python oracle.

Cross-language floats go through the project's established verifier tolerance
(rel_tol=2e-11, abs_tol=2e-10 — tools/verify_rust_engine.py); paths and
positions matched bitwise in development, time_ns differs by ~1 ULP from
CPython-vs-glibc hypot in the momentum magnitude.
"""

import copy
import math

import pytest

from heplab.physics.detector import geometry
from heplab.physics.engine import execute

REL_TOL, ABS_TOL = 2e-11, 2e-10


@pytest.fixture(params=["reference", "rust"])
def backend(request):
    if request.param == "rust":
        pytest.importorskip("heplab_kernels", reason="requires the built kernels wheel")
    return request.param


def _close(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _trim(surface):
    fields = (
        ("radius_m", "half_length_m")
        if surface["kind"] == "cylinder"
        else ("z_m", "inner_radius_m", "outer_radius_m")
    )
    return {"id": surface["id"], "kind": surface["kind"], **{k: surface[k] for k in fields}}


def _request(state_dict, max_path=16.0, step=0.05):
    detector = geometry()
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
    return {
        "op": "trajectory",
        "state": state_dict,
        "surfaces": [_trim(s) for s in detector["surfaces"]],
        "exit_surfaces": [_trim(s) for s in [bore, *faces]],
        "bz_tesla": 3.8,
        "max_path_m": max_path,
        "step_m": step,
    }


def _state(px, py, pz, charge=1.0, position=(0.0, 0.0, 0.0)):
    energy = math.sqrt(px * px + py * py + pz * pz + 0.10565839**2)
    return {
        "position": list(position),
        "momentum": {"energy": energy, "px": px, "py": py, "pz": pz},
        "charge": charge,
        "time_ns": 0.0,
    }


STATES = [
    _state(10.0, 0.0, 1.0, 1.0),
    _state(10.0, 0.0, 1.0, -1.0),
    _state(2.0, 0.5, 4.0, 1.0),
    _state(0.5, -0.5, 0.2, 1.0),
    _state(0.0, 0.0, 12.0, 1.0),
    _state(45.0, 2.0, 8.0, -1.0),
    _state(6.0, 0.0, 0.0, 1.0, position=(1.5, 0.5, 0.4)),
]


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("bz", [0.0, 3.8, -3.8])
@pytest.mark.parametrize("budget,step", [(1.0, 0.005), (16.0, 0.05), (20.0, 0.2)])
def test_trajectory_matches_detector_wrapper(backend, state, bz, budget, step):
    from heplab.physics.detector import trajectory
    from heplab.physics.reference import FourVector, TrackState

    track = TrackState(
        tuple(state["position"]), FourVector(**state["momentum"]), state["charge"], 0.0
    )
    expected = trajectory(track, bz=bz, max_path=budget, step=step, backend="reference")
    actual = trajectory(track, bz=bz, max_path=budget, step=step, backend=backend)
    assert actual.pop("navigation_backend") == backend
    expected.pop("navigation_backend")
    assert _close(expected, actual)
    request = {**_request(state, budget, step), "bz_tesla": bz}
    composite = execute(request, backend=backend)
    assert _close({key: expected[key] for key in composite}, composite)


@pytest.mark.parametrize(
    "field,value",
    [
        ("step_m", 0),
        ("step_m", True),
        ("step_m", float("nan")),
        ("max_path_m", 21),
        ("max_path_m", 0),
        ("bz_tesla", float("inf")),
        ("surfaces", []),
        ("exit_surfaces", []),
        ("state", _state(10, 0, 0, position=(3, 0, 0))),
        ("state", {**_state(10, 0, 0), "charge": True}),
    ],
)
def test_invalid_trajectory_request(backend, field, value):
    with pytest.raises(ValueError):
        execute({**_request(STATES[0]), field: value}, backend=backend)


@pytest.mark.parametrize(
    "update",
    [
        {"extra": 1},
        {"radius_m": True},
        {"radius_m": -1},
        {"half_length_m": float("nan")},
        {"id": 123},
        {"kind": "sphere"},
    ],
)
def test_invalid_surface_rejected_by_both_boundaries(backend, update):
    request = copy.deepcopy(_request(STATES[0]))
    request["surfaces"][0].update(update)
    with pytest.raises(ValueError):
        execute(request, backend=backend)
    if backend == "rust":
        import json

        import heplab_kernels

        # Exercise the Rust deserializer without the Python validation layer.
        with pytest.raises(ValueError):
            heplab_kernels.run_json(json.dumps(request))


def test_parity_comparison_detects_broken_geometry():
    original = execute(_request(STATES[0]))
    broken = copy.deepcopy(original)
    broken["points"][1][0] += 0.001
    assert not _close(original, broken)
