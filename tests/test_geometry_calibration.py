"""Independent geometric oracles and frozen external-reference acceptance gates."""

import json
import math
import threading

import pytest

from heplab.physics.calibration import REFERENCE, calibrate_silicon, muon_response_parameters
from heplab.physics.detector import geometry, silicon_stopping_power, surface_paths, trajectory
from heplab.physics.engine import execute
from heplab.physics.reference import FourVector, TrackState, propagate_uniform_bz


def state(position=(0, 0, 0), momentum=(3, 0, 0), charge=1):
    return TrackState(
        position,
        FourVector(math.hypot(math.sqrt(sum(x * x for x in momentum)), 0.10565839), *momentum),
        charge,
        0,
    )


@pytest.mark.parametrize("field", [0, 3.8, -3.8, 1e-12])
def test_cylinder_intersection_against_independent_radius_formula(field):
    initial = state()
    surface = {"kind": "cylinder", "radius_m": 1.0, "half_length_m": 2.0}
    paths = surface_paths(initial, surface, field, 10)
    expected = (
        1.0
        if abs(field) < 1e-10
        else 2 * (3 / (0.299792458 * abs(field))) * math.asin(0.299792458 * abs(field) / 6)
    )
    assert paths[0] == pytest.approx(expected, abs=1e-9)
    for path in paths:
        moved = propagate_uniform_bz(initial, path, field)
        assert math.hypot(*moved.position[:2]) == pytest.approx(1, abs=1e-9)


def test_tangent_starting_on_surface_finite_extent_and_thin_layers():
    surface = {"kind": "cylinder", "radius_m": 1.0, "half_length_m": 2.0}
    assert surface_paths(state((-2, 1, 0)), surface, 0, 10) == [2.0]
    assert surface_paths(state((1, 0, 0)), surface, 0, 10) == []
    assert surface_paths(state((1, 0, 0), (-3, 0, 0)), surface, 0, 10) == [2.0]
    assert surface_paths(state((0, 0, 3)), surface, 0, 10) == []
    first = surface_paths(state(), surface, 3.8, 10)[0]
    second = surface_paths(state(), {**surface, "radius_m": 1.0000001}, 3.8, 10)[0]
    assert 0 < second - first < 2e-7


def test_annular_disk_oblique_crossing_and_hole():
    disk = {"kind": "disk", "inner_radius_m": 0.06, "outer_radius_m": 0.15, "z_m": 0.345}
    initial = state(momentum=(1, 0, 3))
    paths = surface_paths(initial, disk, 3.8, 2)
    assert len(paths) == 1
    assert paths[0] == pytest.approx(0.345 * math.sqrt(10) / 3)
    assert surface_paths(state(momentum=(0, 0, 3)), disk, 3.8, 2) == []
    assert surface_paths(state(momentum=(1, 0, 0)), disk, 3.8, 2) == []


def test_repeated_helix_turns_and_field_exit_continuity():
    initial = state(momentum=(0.3, 0, 0))
    paths = surface_paths(
        initial, {"kind": "cylinder", "radius_m": 0.1, "half_length_m": 1}, 3.8, 5
    )
    assert len(paths) >= 4
    assert paths == sorted(set(paths))
    traced = trajectory(state(), bz=3.8)
    exit_index = traced["path_m"].index(traced["field_exit_path_m"])
    after = traced["points"][exit_index:]
    # Beyond the bore, points follow a straight line with a continuous tangent.
    a, b, c = after[0], after[1], after[2]
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - b[i] for i in range(3)]
    assert abs(u[0] * v[1] - u[1] * v[0]) < 1e-12
    assert len(traced["crossings"]) >= 4


def test_geometry_provenance_and_pdg_calibration_split():
    model = geometry()
    assert [s["radius_m"] for s in model["surfaces"][:3]] == [0.044, 0.073, 0.102]
    assert len(model["sha256"]) == 64
    calibrated = calibrate_silicon()
    assert calibrated["status"] == "reference_calibrated"
    assert set(calibrated["training_rows"]).isdisjoint(calibrated["heldout_rows"])
    assert len(calibrated["heldout_rows"]) == 24
    assert calibrated["max_abs_relative_error"] < 0.02
    value, _ = silicon_stopping_power(0.1)
    assert value == pytest.approx(1.849 * 2.329 * 0.1)
    for energy in (0.099, 100.01, math.nan):
        with pytest.raises(ValueError):
            silicon_stopping_power(energy)


def test_response_payload_passes_frozen_gates_and_scales_engine():
    payload = json.loads((REFERENCE / "muon-response-calibration.json").read_text())
    assert payload["status"] == "reference_calibrated"
    assert payload["training_sha256"] != payload["heldout_sha256"]
    assert all(row["passed"] for row in payload["bins"])
    parameters = muon_response_parameters(45, 0)
    assert 0 < parameters["efficiency"] < 1
    assert parameters["relative_pt_resolution"] > 0
    for pt, eta in ((4, 0), (201, 0), (45, 2.4)):
        with pytest.raises(ValueError):
            muon_response_parameters(pt, eta)
    pytest.importorskip("pydantic")
    from heplab.server.workbench import RunConfig, bench

    result = bench(RunConfig(response_model="delphes_reference"), threading.Event())
    assert (
        result["tracks"][0]["reference_response"]["parameters"]["calibration_id"] == payload["id"]
    )


@pytest.mark.parametrize(
    "surface",
    [
        {"kind": "cylinder", "radius_m": 0.0, "half_length_m": 1.0},
        {"kind": "cylinder", "radius_m": 1.0, "half_length_m": -1.0},
        {"kind": "disk", "z_m": 1.0, "inner_radius_m": 2.0, "outer_radius_m": 1.0},
        {"kind": "sphere", "radius_m": 1.0},
    ],
)
def test_invalid_surface_domains_reject(surface):
    from dataclasses import asdict

    with pytest.raises(ValueError):
        execute(
            {
                "op": "intersect",
                "state": asdict(state()),
                "surface": surface,
                "bz_tesla": 3.8,
                "max_path_m": 10.0,
            }
        )


def test_calibrated_scale_converts_log_bias_to_positive_response_mean():
    from dataclasses import asdict

    value = execute(
        {
            "op": "simulate",
            "particles": [{"object_id": 1, "state": asdict(state())}],
            "config": {
                "seed": 42,
                "event_key": "scale-test",
                "efficiency": 1.0,
                "relative_pt_resolution": 0.0,
                "momentum_scale": 1.02,
                "path_length_m": 0.0,
                "bz_tesla": 0.0,
                "max_objects": 1,
            },
        }
    )
    assert value["objects"][0]["state"]["momentum"]["px"] == pytest.approx(3.06)


def test_coupled_slab_path_and_predicted_crossings_preserve_order_and_ledger():
    pytest.importorskip("pydantic")
    from heplab.server.workbench import RunConfig, bench

    value = bench(RunConfig(momentum_gev=5.0), threading.Event())
    track = value["tracks"][0]
    traced = track["trajectory"]
    assert traced["model"] == "ideal-solenoid-with-single-silicon-slab-v1"
    assert traced["path_m"] == sorted(traced["path_m"])
    assert len(traced["path_m"]) == len(traced["points"])
    offset = traced["path_m"].index(1.001)
    assert traced["points"][offset] == pytest.approx(track["material"]["state"]["position"])
    assert track["material"]["deposit_gev"] > 0
    assert abs(track["material"]["energy_residual_gev"]) < 1e-12
    assert [c["surface_id"] for c in traced["crossings"][:3]] == ["BPIX1", "BPIX2", "BPIX3"]


def test_curler_reaches_path_budget_without_claiming_field_exit():
    traced = trajectory(state(momentum=(1.0, 0.0, 0.0)), bz=3.8)
    assert traced["field_exit_path_m"] is None
    assert traced["termination"] == "path_budget_inside_field"
    assert traced["field_bz_tesla"] == 3.8
    assert max(math.hypot(*point[:2]) for point in traced["points"]) < 3
    with pytest.raises(ValueError, match="turn budget"):
        surface_paths(
            state(momentum=(1e-6, 0.0, 0.0)),
            {"kind": "cylinder", "radius_m": 1e-7, "half_length_m": 1.0},
            3.8,
            100.0,
        )
