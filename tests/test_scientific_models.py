"""Regression checks for the bounded scientific models and their metadata."""

import math

import pytest

from heplab.physics.constants import (
    CONSTANTS_ID,
    MUON_MASS_GEV,
    MUON_MEAN_LIFETIME_S,
    SPEED_OF_LIGHT_M_PER_S,
    constants_record,
)
from heplab.physics.curvature import curvature_sweep
from heplab.physics.lifetime import (
    decay_probability,
    mean_decay_path_m,
    path_from_altitudes_m,
    run_survival_experiment,
    survival_probability,
)
from heplab.server.workbench import RunConfig, bench, lifetime_experiment


def test_muon_constants_are_versioned_and_sourced_with_units_and_uncertainties():
    record = constants_record()
    assert record["id"] == CONSTANTS_ID == "pdg-2025"
    assert "pdg.lbl.gov/2025" in record["source"]
    values = {item["name"]: item for item in record["values"]}
    assert values["muon_mass"]["value"] == MUON_MASS_GEV
    assert values["muon_mass"]["unit"] == "GeV/c^2"
    assert 0 < values["muon_mass"]["uncertainty"] < 1e-8
    assert values["muon_mean_lifetime"]["value"] == MUON_MEAN_LIFETIME_S
    assert values["muon_mean_lifetime"]["unit"] == "s"
    assert 0 < values["muon_mean_lifetime"]["uncertainty"] < 1e-10


def test_lifetime_model_matches_analytic_survival_and_has_seeded_sampling_scope():
    momentum, path = 1.0, 15_000.0
    mean_path = (momentum / MUON_MASS_GEV) * SPEED_OF_LIGHT_M_PER_S * MUON_MEAN_LIFETIME_S
    assert mean_decay_path_m(momentum) == pytest.approx(mean_path, rel=1e-15)
    expected = math.exp(-path / mean_path)
    assert survival_probability(momentum, path) == pytest.approx(expected, rel=1e-15)
    assert decay_probability(momentum, path) == pytest.approx(-math.expm1(-path / mean_path))
    assert survival_probability(momentum, path) + decay_probability(
        momentum, path
    ) == pytest.approx(1)

    first = run_survival_experiment(
        momentum_gev_c=momentum, path_length_m=path, seed=1234, sample_size=100_000
    )
    repeated = run_survival_experiment(
        momentum_gev_c=momentum, path_length_m=path, seed=1234, sample_size=100_000
    )
    assert first == repeated
    summary = first["summary"]
    low, high = summary["survival_wilson_95_percent"]
    assert low <= expected <= high
    assert first["model_spec"]["domain"]["momentum_is_constant"] is True
    assert (
        "atmospheric production spectrum and hadronic shower"
        in first["model_spec"]["omitted_effects"]
    )


def test_plane_parallel_altitude_path_is_explicitly_bounded():
    assert path_from_altitudes_m(15_000, 0, 0) == pytest.approx(15_000)
    assert path_from_altitudes_m(15_000, 1_000, math.radians(60)) == pytest.approx(28_000)
    with pytest.raises(ValueError, match="above detector"):
        path_from_altitudes_m(1_000, 1_000, 0)
    with pytest.raises(ValueError, match="below 75"):
        path_from_altitudes_m(15_000, 0, math.radians(75))


def test_curvature_sweep_covers_charge_momentum_and_field_with_sourced_scope():
    result = curvature_sweep()
    assert len(result["ideal_uniform_field"]) == 4 * 4 * 2
    assert len(result["tracker_oae_reference"]) == 4 * 2
    assert result["config"]["momenta_gev_c"] == [1.0, 5.0, 20.0, 100.0]
    assert result["config"]["uniform_fields_t"] == [0.0, 2.0, 3.8, 5.0]
    assert result["config"]["charges_e"] == [-1.0, 1.0]
    assert "not independently validated" in result["limits"][1]

    rows = result["ideal_uniform_field"]
    for momentum in result["config"]["momenta_gev_c"]:
        for field in result["config"]["uniform_fields_t"]:
            positive = next(
                row
                for row in rows
                if row["momentum_gev_c"] == momentum
                and row["field_t"] == field
                and row["charge_e"] == 1.0
            )
            negative = next(
                row
                for row in rows
                if row["momentum_gev_c"] == momentum
                and row["field_t"] == field
                and row["charge_e"] == -1.0
            )
            assert positive["signed_sagitta_m"] == pytest.approx(
                -negative["signed_sagitta_m"], abs=2e-15
            )
            if field == 0:
                assert positive["signed_sagitta_m"] == 0
            else:
                assert positive["signed_sagitta_m"] * field > 0
    assert {row["termination"] for row in result["tracker_oae_reference"]} == {"path_budget"}

    with pytest.raises(ValueError, match="momentum grid"):
        curvature_sweep(momenta_gev_c=(101.0,))


def test_workbench_lifetime_endpoint_keeps_altitude_geometry_out_of_atmospheric_claims():
    result = lifetime_experiment(
        {
            "path_mode": "altitude",
            "momentum_gev_c": 1.0,
            "production_altitude_km": 15.0,
            "detector_altitude_km": 0.0,
            "zenith_deg": 30.0,
            "seed": 8,
            "sample_size": 100,
        }
    )
    assert result["config"]["path_length_m"] == pytest.approx(15_000 / math.cos(math.radians(30)))
    assert result["model_spec"]["domain"]["path_source"].startswith("plane-parallel")
    assert result["artifact"]["parent_run_sha256"] is None
    with pytest.raises(ValueError):
        lifetime_experiment({"path_mode": "fixed", "unknown": 1})


def test_run_model_spec_names_each_component_domain_and_constant_source():
    config = RunConfig()
    import threading

    result = bench(config, threading.Event())
    spec = result["model_spec"]
    assert spec["schema"] == "heplab-model-spec-v1"
    ids = {item["id"] for item in spec["components"]}
    assert ids >= {
        "declared-muon-pair-v1",
        "ideal-solenoid-helix-v1",
        "pdg-si-muon-loglinear-split-v1",
        "thin-slab-highland-v1",
        "deposit-electronics-v1",
    }
    assert spec["constants"]["id"] == CONSTANTS_ID
    assert spec["overall_status"] == "not_a_global_validation_claim"


def test_split_run_configuration_round_trips_and_legacy_flat_input_is_migrated():
    flat = RunConfig()
    assert flat.to_envelope()["display"]["projection"] == "xy-xz"
    envelope = flat.to_envelope(projection="xz", region="tracker")
    assert envelope["schema"] == "heplab-run-config-v2"
    assert envelope["display"] == {"projection": "xz", "region": "tracker"}
    assert RunConfig.model_validate(envelope).model_dump() == flat.model_dump()
    assert RunConfig.model_validate(flat.model_dump()).model_dump() == flat.model_dump()
    with pytest.raises(ValueError, match="display configuration"):
        RunConfig.model_validate({**envelope, "display": {"projection": "equirectangular"}})
    paired = flat.to_envelope(projection="xy-xz")
    assert RunConfig.model_validate(paired).model_dump() == flat.model_dump()
