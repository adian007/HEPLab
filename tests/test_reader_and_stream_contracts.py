"""Real-format offline fixtures for native reader and source-range contracts."""

import json
import zlib

import pytest
import yaml

ak = pytest.importorskip("awkward")
np = pytest.importorskip("numpy")
uproot = pytest.importorskip("uproot")

from heplab.io.xrootd import iter_chunks  # noqa: E402
from heplab.readers.nanoaod import normalize_entry  # noqa: E402


def nano_columns(count=4):
    return {
        "run": np.ones(count, dtype=np.uint32),
        "luminosityBlock": np.full(count, 5, dtype=np.uint32),
        "event": np.arange(count, dtype=np.uint64),
        "Muon_pt": ak.Array([[45.6, 45.6]] * count),
        "Muon_eta": ak.Array([[0.0, 0.0]] * count),
        "Muon_phi": ak.Array([[0.0, 3.14159]] * count),
        "Muon_mass": ak.Array([[0.105658, 0.105658]] * count),
        "Muon_charge": ak.Array([[1, -1]] * count),
        "HLT_Test": np.ones(count, dtype=bool),
    }


def test_SCHEMA_003_optional_absence_does_not_change_object_count():
    row = ak.Array(nano_columns(1))[0]
    event = normalize_entry(row)
    assert len(event["Muon"]) == 2
    assert all(obj["iso"] is None and obj["quality_flags"] is None for obj in event["Muon"])
    assert event["Photon"] is None
    assert event["Trigger"] == {"names": ["HLT_Test"], "fired": [True], "source": "recorded"}


def test_SCHEMA_004_jagged_mismatch_is_not_truncated():
    columns = nano_columns(1)
    columns["Muon_eta"] = ak.Array([[0.0]])
    with pytest.raises(ValueError, match="shape"):
        normalize_entry(ak.Array(columns)[0])


def test_SCHEMA_006_generator_weight_preserved():
    columns = nano_columns(1)
    columns["genWeight"] = np.array([-2.5])
    event = normalize_entry(ak.Array(columns)[0], is_data=False)
    assert event["EventInfo"]["weight"] == -2.5
    with pytest.raises(ValueError, match="generator weights"):
        normalize_entry(ak.Array(nano_columns(1))[0], is_data=False)


def test_DATA_002_N_then_M_and_full_have_exact_coverage(tmp_path, monkeypatch):
    root_path = tmp_path / "tiny.root"
    with uproot.recreate(root_path) as root:
        root["Events"] = nano_columns()
    manifest = {
        "schema": "heplab-dataset-manifest/v0",
        "name": "fixture",
        "kind": "data",
        "format": "NANOAOD",
        "record": 1,
        "files": [
            {
                "url": str(root_path),
                "size_bytes": root_path.stat().st_size,
                "entries": 4,
                "adler32": f"{zlib.adler32(root_path.read_bytes()) & 0xFFFFFFFF:08x}",
            }
        ],
    }
    folder = tmp_path / "catalog"
    folder.mkdir()
    (folder / "fixture.yaml").write_text(yaml.safe_dump(manifest))
    monkeypatch.setenv("HEPLAB_MANIFEST_DIR", str(folder))
    monkeypatch.setenv("HEPLAB_CACHE_DIR", str(tmp_path / "cache"))
    assert sum(len(chunk) for _, chunk in iter_chunks("fixture", sample=2, chunk_size=2)) == 2
    assert sum(len(chunk) for _, chunk in iter_chunks("fixture", sample=4, chunk_size=2)) == 4
    complete = list(iter_chunks("fixture", chunk_size=2))
    assert [(d["entry_start"], d["entry_stop"]) for d, _ in complete] == [(0, 2), (2, 4)]
    assert [event["EventInfo"]["event"] for _, chunk in complete for event in chunk] == [0, 1, 2, 3]
    assert all(d["integrity"] == "declared_only" for d, _ in complete)
    with pytest.raises(ValueError, match="fewer events"):
        list(iter_chunks("fixture", sample=5))
    with pytest.raises(ValueError, match="disagrees"):
        list(iter_chunks("fixture", sample=1, is_data=False))


def test_SCHEMA_003_DELPHES_isolation_does_not_fabricate_ID_or_pixel_seed(tmp_path):
    from heplab.readers.delphes import read

    path = tmp_path / "delphes.root"
    with uproot.recreate(path) as root:
        root["Delphes"] = {
            "Muon.PT": ak.Array([[45.6]]),
            "Muon.Eta": ak.Array([[0.0]]),
            "Muon.Phi": ak.Array([[0.0]]),
            "Muon.Charge": ak.Array([[1]]),
            "Muon.IsolationVar": ak.Array([[0.05]]),
            "Photon.PT": ak.Array([[30.0]]),
            "Photon.Eta": ak.Array([[0.2]]),
            "Photon.Phi": ak.Array([[1.0]]),
            "Photon.IsolationVar": ak.Array([[0.1]]),
            "Event.Weight": ak.Array([[-1.0]]),
        }
    event = next(read(path))
    assert event["Muon"][0]["iso"] == 0.05
    assert event["Muon"][0]["quality_flags"] is None
    assert event["Photon"][0]["has_pixel_seed"] is None
    assert event["EventInfo"]["weight"] == -1


def test_API_002_no_fit_parent_overwrite_for_explicit_same_path(tmp_path):
    from heplab.cli import main

    pytest.importorskip("iminuit")
    pytest.importorskip("scipy")
    path = tmp_path / "parent.json"
    path.write_text(json.dumps({"masses": np.random.default_rng(1).normal(91, 2, 100).tolist()}))
    original = path.read_bytes()
    assert main(["fit", str(path), "--output", str(path)]) == 2
    assert path.read_bytes() == original
