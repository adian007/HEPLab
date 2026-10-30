"""Public engine and uncertainty-comparison checks beyond the numerical oracle."""

import copy
import json
import sys
import types

import pytest

from heplab.physics.engine import execute


def test_incompatible_native_extension_is_reported_as_unavailable(monkeypatch):
    from heplab.physics import engine

    monkeypatch.setitem(sys.modules, "heplab_kernels", types.ModuleType("heplab_kernels"))
    engine._rust_binding.cache_clear()
    try:
        assert engine._rust_binding() == (
            False,
            "Native Rust binding is incompatible: run_json is missing",
        )
    finally:
        engine._rust_binding.cache_clear()


def test_RESPONSE_003_reference_response_is_order_invariant_and_positive():
    state = {
        "position": [0, 0, 0],
        "momentum": {"energy": 5, "px": 3, "py": 0, "pz": 0},
        "charge": 1,
        "time_ns": 0,
    }
    request = {
        "op": "simulate",
        "particles": [{"object_id": i, "state": state} for i in range(10)],
        "config": {
            "seed": 42,
            "event_key": "toy",
            "efficiency": 1,
            "relative_pt_resolution": 0.1,
            "path_length_m": 1,
            "bz_tesla": 2,
            "max_objects": 20,
        },
    }
    first = execute(request)
    request["particles"].reverse()
    second = execute(request)
    assert first["objects"] == list(reversed(second["objects"]))
    assert all(obj["state"]["momentum"]["energy"] > 0 for obj in first["objects"])
    assert first["validation"] == "educational_unvalidated"


def test_CORE_006_unknown_native_protocol_fields_reject_before_dispatch():
    with pytest.raises(ValueError, match="unknown engine request"):
        execute({"op": "mass", "first": [1, 0, 0, 1], "second": [1, 0, 0, 1], "arbitrary": 1})


def test_STAT_004_normalized_comparison_has_zero_sum_covariance_and_null_ratios(tmp_path):
    np = pytest.importorskip("numpy")
    from heplab.analyses.closure import compare

    base = {
        "histogram": {
            "observable": "dimuon_mass",
            "units": "GeV",
            "edges": [0, 1, 2, 3],
            "counts": [0, 2, 3],
            "sumw2": [0, 2, 3],
        },
        "analysis_config_sha256": "a" * 64,
        "candidate_policy": "highest_sum_pt",
        "semantics": {"muon_iso": ["cms_pfRelIso04"], "units": "GeV"},
        "data_kind": "data",
    }
    data = tmp_path / "data.json"
    sim = tmp_path / "sim.json"
    data.write_text(json.dumps(base))
    simulation = copy.deepcopy(base)
    simulation["data_kind"] = "simulation"
    sim.write_text(json.dumps(simulation))
    report = compare(data, sim)
    assert report["normalized_bin_ratio_sim_over_data"] == [None, 1, 1]
    assert np.allclose(np.asarray(report["data_normalized_covariance"]).sum(axis=0), 0)
    assert report["ratio_variance"][1] > 0
    simulation["semantics"]["muon_iso"] = ["delphes_card_isolation"]
    sim.write_text(json.dumps(simulation))
    with pytest.raises(ValueError, match="semantics"):
        compare(data, sim)


def test_GEN_005_simulation_preflight_refuses_unbuilt_unpinned_runtime():
    from heplab.sim import generate

    with pytest.raises(RuntimeError, match="pinned"):
        generate(events=10, image="not-a-published-simulator")
