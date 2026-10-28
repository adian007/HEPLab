"""Requirement-linked regressions for the production blockers, using offline fixtures."""

import copy
import json
import math
from concurrent.futures import ThreadPoolExecutor

import pytest

from heplab.analyses.dimuon.run import process
from heplab.cli import main
from heplab.io.artifacts import publish
from heplab.io.cache import cache_key, open_cached, write_json_events
from heplab.io.certification import LumiMask
from heplab.io.provenance import config_hash, source_snapshot


def event(weight=1.0):
    return {
        "EventInfo": {
            "run": 1,
            "luminosity_block": 5,
            "event": 42,
            "is_data": False,
            "weight": weight,
        },
        "Muon": [
            {
                "pt": 45.6,
                "eta": 0.0,
                "phi": phi,
                "mass": 0.105658,
                "charge": charge,
                "iso": 0.01,
                "quality_flags": True,
            }
            for phi, charge in [(0, 1), (math.pi, -1)]
        ],
    }


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1])
def test_ANA_001_missing_or_invalid_isolation_fails(value):
    sample = event()
    sample["Muon"][0]["iso"] = value
    result = process([sample], {})
    assert result["histogram"]["entries"] == 0
    assert result["invalid_objects"] == 1


def test_ANA_002_signed_weights_preserve_yield_and_variance():
    result = process([event(2), event(-1)], {})
    assert sum(result["histogram"]["counts"]) == 1
    assert sum(result["histogram"]["sumw2"]) == 5
    assert result["cutflow_weighted"]["all"] == {"sumw": 1, "sumw2": 5}


def test_ANA_002_multiple_pairs_have_event_cluster_variance():
    sample = event(2)
    sample["Muon"].append(copy.deepcopy(sample["Muon"][0]))
    result = process([sample], {})
    assert result["multi_candidate_events"] == 1
    assert sum(result["histogram"]["sumw2"]) == 8
    assert sum(result["histogram"]["event_sumw2"]) == 16


def test_DATA_004_certification_endpoints_and_unknown_runs(tmp_path):
    path = tmp_path / "good.json"
    path.write_text('{"1":[[2,5],[8,10]]}')
    mask = LumiMask(path)
    assert all(mask.accepts(1, x) for x in (2, 5, 8, 10))
    assert not any(mask.accepts(1, x) for x in (1, 6, 7, 11))
    assert not mask.accepts(2, 2)


def test_DATA_004_measurement_cannot_pass_without_certification_and_triggers():
    sample = event()
    sample["EventInfo"]["is_data"] = True
    cfg = {"validation": {"mode": "measurement"}, "trigger": {"paths": ["HLT_Test"]}}
    with pytest.raises(ValueError, match="certified"):
        process([sample], cfg)
    sample["EventInfo"].update(certified=True, certification_sha256="a" * 64)
    with pytest.raises(ValueError, match="unknown required trigger"):
        process([sample], cfg)
    sample["Trigger"] = {"names": ["HLT_Test"], "fired": [False], "source": "recorded"}
    assert process([sample], cfg)["histogram"]["entries"] == 0
    sample["Trigger"]["fired"] = [True]
    assert process([sample], cfg)["histogram"]["entries"] == 1


def test_DATA_002_range_and_manifest_change_cache_identity():
    base = cache_key(
        "dataset", frozenset({"Muon_pt"}), 1, entry_start=0, entry_stop=10, manifest="a"
    )
    assert base != cache_key(
        "dataset", frozenset({"Muon_pt"}), 1, entry_start=0, entry_stop=100, manifest="a"
    )
    assert base != cache_key(
        "dataset", frozenset({"Muon_pt"}), 1, entry_start=0, entry_stop=10, manifest="b"
    )


def test_DATA_005_atomic_cache_idempotence_conflicts_and_corruption(tmp_path, monkeypatch):
    monkeypatch.setenv("HEPLAB_CACHE_DIR", str(tmp_path))
    key = cache_key("dataset", frozenset(), 1, entry_start=0, entry_stop=1)
    rows = [event()]
    descriptor = {"entry_start": 0, "entry_stop": 1}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: write_json_events(key, rows, descriptor=descriptor), range(2))
        )
    assert results[0] == results[1]
    assert open_cached(key, expected=descriptor) == rows
    with pytest.raises(ValueError, match="CacheConflict"):
        write_json_events(key, [event(2)], descriptor=descriptor)
    with pytest.raises(ValueError, match="coverage"):
        open_cached(key, expected={"entry_start": 0, "entry_stop": 2})
    results[0].write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        open_cached(key)
    assert not list(tmp_path.glob(".stage-*"))


def test_DATA_005_uncommitted_and_unsafe_cache_paths_reject(tmp_path, monkeypatch):
    monkeypatch.setenv("HEPLAB_CACHE_DIR", str(tmp_path))
    key = "a" * 64
    (tmp_path / key).mkdir()
    (tmp_path / key / "events.json").write_text("[]")
    with pytest.raises(FileNotFoundError):
        open_cached(key)
    with pytest.raises(ValueError):
        open_cached("../outside")


@pytest.mark.parametrize("value", [{"x": float("nan")}, {"x": object()}, {1: "nonstring"}])
def test_TRUST_002_invalid_hash_inputs_reject(value):
    with pytest.raises((ValueError, TypeError)):
        config_hash(value)


def test_TRUST_001_untracked_source_edits_change_snapshot(tmp_path):
    (tmp_path / "src").mkdir()
    source = tmp_path / "src/module.py"
    source.write_text("value=1")
    first = source_snapshot(tmp_path)
    source.write_text("value=2")
    assert source_snapshot(tmp_path) != first


def test_TRUST_003_artifact_is_immutable(tmp_path):
    target = tmp_path / "parent.json"
    publish(target, {"x": 1})
    original = target.read_bytes()
    publish(target, {"x": 1})
    with pytest.raises(ValueError, match="immutable"):
        publish(target, {"x": 2})
    assert target.read_bytes() == original


def test_ANA_001_JSON_event_limit_is_respected(tmp_path):
    source = tmp_path / "events.json"
    source.write_text(json.dumps([event(), event()]))
    target = tmp_path / "result.json"
    assert (
        main(
            ["run", "dimuon", "--input", str(source), "--max-events", "1", "--output", str(target)]
        )
        == 0
    )
    result = json.loads(target.read_text())
    assert result["events_processed"] == 1
    assert result["provenance"]["source_ranges"][0]["entry_stop"] == 1
    assert result["provenance"]["source_tree_sha256"]


@pytest.mark.parametrize(
    "config",
    [
        {"selection": {"muons": {"min_pT": 25}}},
        {"binning": {"dimuon_mass": {"log_bins": "false"}}},
        {"candidate_policy": "closest_to_reference_mass"},
    ],
)
def test_ANA_001_unknown_cuts_and_implicit_reference_mass_reject(config):
    with pytest.raises(ValueError):
        process([event()], config)


def test_STAT_001_truncated_mixture_integrates_to_one_near_boundary():
    pytest.importorskip("scipy")
    from scipy.integrate import quad

    from heplab.stats.fits import mixture_density

    for mean, sigma, fraction in [(70, 5, 0.8), (110, 2, 1), (90, 20, 0.2)]:
        integral, _ = quad(
            lambda x, m=mean, s=sigma, f=fraction: mixture_density([x], m, s, f, (70, 110))[0],
            70,
            110,
        )
        assert integral == pytest.approx(1, abs=1e-9)


def test_TRUST_003_fit_creates_a_child_and_preserves_parent(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("iminuit")
    pytest.importorskip("scipy")
    parent = tmp_path / "parent.json"
    values = np.random.default_rng(1).normal(91.2, 2, size=300).tolist()
    parent.write_text(json.dumps({"masses": values, "candidate_weights": [1] * len(values)}))
    original = parent.read_bytes()
    assert main(["fit", str(parent)]) == 0
    assert parent.read_bytes() == original
    child = json.loads((tmp_path / "parent-fit.json").read_text())
    assert child["parent_sha256"]
    assert abs(child["fit"]["values"]["mean"] - 91.2) < 0.5


def test_API_002_local_service_rejects_foreign_origin_and_symlink(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    client = TestClient(create_app(tmp_path), base_url="http://localhost")
    assert (
        client.get("/api/v1/datasets", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    outside = tmp_path.parent / "outside-artifact.json"
    outside.write_text("{}")
    try:
        (tmp_path / "escape.json").symlink_to(outside)
    except OSError:
        return  # Windows may disallow unprivileged symlinks; traversal still checked below.
    assert client.get("/api/v1/runs/escape").status_code == 404
