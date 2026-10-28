"""Independent CMS field values, bounded transport and sourced display assets."""

import json
import math
import threading
from dataclasses import asdict

import pytest

from heplab.physics.calibration import REFERENCE
from heplab.physics.cms_field import trace_tracker, tracker_field
from heplab.physics.cms_sources import display_asset, display_manifest
from heplab.physics.engine import execute
from heplab.physics.reference import FourVector, TrackState


def test_cms_reference_vectors_not_generated_by_implementation():
    fixture = json.loads((REFERENCE / "cms-field-points.json").read_text(encoding="utf8"))
    assert len(fixture["points"]) == 128
    for row in fixture["points"]:
        predicted = tracker_field(row[:3])
        assert math.dist(predicted, row[3:]) < 2e-6


@pytest.mark.parametrize(
    "position", [[1.15, 0, 0], [0, 0, -2.8], [True, 0, 0], [float("nan"), 0, 0], [0, 0], "000"]
)
def test_cms_field_rejects_extrapolation_and_invalid_inputs(position):
    with pytest.raises(ValueError):
        execute({"op": "cms_tracker_field", "position_m": position})


def test_nonuniform_transport_against_independent_adaptive_solver():
    np = pytest.importorskip("numpy")
    scipy = pytest.importorskip("scipy.integrate")
    vector = FourVector.from_pt_eta_phi_mass(0.4, 0.8, 0.7, 0.10565839)
    initial = TrackState((0.01, -0.03, 0.1), vector, -1, 2)
    momentum = vector.momentum

    def derivative(_path, values):
        u = values[3:] / np.linalg.norm(values[3:])
        force = 0.299792458 * initial.charge * np.cross(u, tracker_field(values[:3].tolist()))
        return np.concatenate((u, force))

    expected = scipy.solve_ivp(
        derivative,
        (0, 0.6),
        [*initial.position, vector.px, vector.py, vector.pz],
        method="DOP853",
        rtol=1e-12,
        atol=1e-13,
    ).y[:, -1]
    traced = trace_tracker(initial, 0.6, 0.005)
    final = traced["state"]
    assert math.dist(final["position"], expected[:3]) < 2e-9
    assert math.dist([final["momentum"][k] for k in ("px", "py", "pz")], expected[3:]) < 2e-9
    assert math.hypot(*(final["momentum"][k] for k in ("px", "py", "pz"))) == pytest.approx(
        momentum, rel=1e-14
    )
    assert final["time_ns"] == pytest.approx(2 + 0.6 * vector.energy / (momentum * 0.299792458))


def test_transport_stops_at_validity_edge_without_zero_field_fallback():
    initial = TrackState((0, 0, 0), FourVector.from_pt_eta_phi_mass(45, 0, 0, 0.105), 1, 0)
    result = trace_tracker(initial, 16, 0.005)
    assert result["termination"] == "field_validity_boundary"
    assert 1.15 - 2e-7 < math.hypot(*result["state"]["position"][:2]) < 1.15
    assert result["actual_path_m"] < 1.16
    with pytest.raises(ValueError):
        execute(
            {
                "op": "trace_cms_tracker",
                "state": asdict(initial),
                "path_length_m": 1,
                "step_m": True,
            }
        )


def test_display_layer_integrity_extent_and_transport_separation():
    manifest = display_manifest()
    assert manifest["transport_compatible"] is False
    assert {row["id"] for row in manifest["layers"]} == {
        "pixel",
        "strips",
        "ecal",
        "hcal",
        "dt",
        "csc",
        "rpc",
    }
    assert sum(row["vertices"] for row in manifest["layers"]) == 825728
    for layer in manifest["layers"]:
        assert display_asset(layer["id"]).stat().st_size == layer["bytes"]
    with pytest.raises(ValueError):
        display_asset("../../LICENSE")
    pixel = manifest["layers"][0]
    assert max(pixel["bounds_m"][1]) < 0.6
    assert max(row["bounds_m"][1][2] for row in manifest["layers"]) > 10


def test_bench_oae_preserves_material_ledger_and_crossing_semantics():
    pytest.importorskip("pydantic", minversion="2")
    from heplab.server.workbench import RunConfig, bench

    result = bench(RunConfig(field_model="cms_tracker"), threading.Event())
    assert result["validation"] == "educational_unvalidated"
    for track in result["tracks"]:
        assert abs(track["material"]["energy_residual_gev"]) < 1e-12
        assert track["trajectory"]["termination"] == "field_validity_boundary"
        assert len(track["trajectory"]["crossings"]) == 4
        assert "polyline" in track["trajectory"]["crossing_method"]
    with pytest.raises(ValueError):
        RunConfig(field_model="cms_tracker", bz_tesla=4.0)
