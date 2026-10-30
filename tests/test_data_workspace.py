"""Data selection, certification, caching, import integrity and IPC boundaries."""

import base64
import json
import math

import pytest

pytest.importorskip("pydantic", minversion="2")

from heplab.desktop.worker import operations  # noqa: E402
from heplab.io.provenance import file_hash  # noqa: E402
from heplab.server.data_workspace import CERT, DataWorkspace, Selection, histogram  # noqa: E402

ak = pytest.importorskip("awkward")
np = pytest.importorskip("numpy")
uproot = pytest.importorskip("uproot")


@pytest.fixture
def samples(tmp_path, monkeypatch):
    folder = tmp_path / "samples"
    folder.mkdir()
    (folder / CERT).write_text(json.dumps({"1": [[1, 10]]}))
    pts = [[45.0, 45.0], [45.0, 45.0], [70.0, 70.0, 30.0], [10.0, 10.0], [45.0, 45.0]]
    content = {
        "run": np.array([1, 2, 1, 1, 1], dtype=np.uint32),
        "luminosityBlock": np.ones(5, dtype=np.uint32),
        "event": np.arange(11, 16, dtype=np.uint64),
        "Muon_pt": ak.Array(pts),
        "Muon_eta": ak.Array([[0.0] * len(row) for row in pts]),
        "Muon_phi": ak.Array(
            [
                [0.0, math.pi],
                [0.0, math.pi],
                [0.0, math.pi, math.pi],
                [0.0, math.pi],
                [0.0, math.pi],
            ]
        ),
        "Muon_mass": ak.Array([[0.105658] * len(row) for row in pts]),
        "Muon_charge": ak.Array([[1, -1], [1, -1], [1, -1, -1], [1, -1], [1, -1]]),
        "Muon_tightId": ak.Array([[True] * len(row) for row in pts]),
        "Muon_pfRelIso04_all": ak.Array([[0.1] * len(row) for row in pts]),
        "HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ": np.array([True, True, True, True, False]),
        "HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ": np.zeros(5, dtype=bool),
    }
    for filename, metadata, kind in [
        ("run2016g-100k.root", "source.json", "data"),
        ("dy-ul16-100k.root", "dy-source.json", "mc"),
    ]:
        with uproot.recreate(folder / filename) as file:
            file["Events"] = {
                **content,
                **({"genWeight": np.array([2.0, -0.5, 1.0, 1.0, 1.0])} if kind == "mc" else {}),
            }
        (folder / metadata).write_text(
            json.dumps({"derived_file_sha256": file_hash(folder / filename)})
        )
    monkeypatch.setenv("HEPLAB_CMS_SAMPLE_DIR", str(folder))
    return folder


def test_common_selection_certification_signed_weights_and_reuse(tmp_path, samples):
    workspace = DataWorkspace(tmp_path)
    report = workspace.analyze({})
    assert report["populations"]["data"]["selected_events"] == 1
    assert report["populations"]["mc"]["selected_events"] == 2
    assert report["populations"]["mc"]["cutflow"][-1]["sumw"] == 1.5
    assert report["populations"]["data"]["cutflow"][1]["events"] == 4
    assert report["root_reads"] == 2
    # Highest-pT pair has mass 140; the alternative in-window pair must not win.
    assert report["populations"]["data"]["cutflow"][-2]["events"] == 2
    tight = workspace.analyze({"min_pt": 50.0, "leading_pt": 50.0})
    assert tight["populations"]["data"]["selected_events"] == 0
    assert tight["root_reads"] == 2 and workspace.load("cms-run2016g")["reused"]
    assert all(row["value"] is None for row in tight["mass_ratio"])
    reopened = DataWorkspace(tmp_path)
    assert reopened.get(report["id"]) == report
    assert reopened.rows(report["id"], "data")["total"] == 1
    with pytest.raises(ValueError):
        reopened.get("../../secret")


def test_normalized_weight_covariance_and_flow_bins():
    h = histogram(np.array([-1.0, 0.5, 1.5, 2.0]), np.array([1.0, 2.0, -0.5, 1.0]), [0.0, 1.0, 2.0])
    assert h["entries"] == [1, 1, 1, 1]
    assert h["sumw"] == [1.0, 2.0, -0.5, 1.0]
    covariance = np.array(h["covariance"])
    assert np.allclose(covariance.sum(axis=0), 0)
    assert np.linalg.eigvalsh(covariance).min() > -1e-12
    assert sum(h["fractions"]) == pytest.approx(1)
    assert histogram(np.array([0.5]), np.array([-1.0]), [0.0, 1.0])["fractions"] is None


def test_certification_resolves_installed_package_and_prefers_sample_override(
    tmp_path, monkeypatch
):
    from heplab.server import data_workspace

    package = tmp_path / "site-packages" / "heplab"
    sample = package / "data" / "cms-samples"
    packaged = package / "data" / "certification" / CERT
    packaged.parent.mkdir(parents=True)
    packaged.write_text('{"1": [[1, 10]]}', encoding="utf-8")
    monkeypatch.setattr(data_workspace, "__file__", str(package / "server" / "data_workspace.py"))
    assert data_workspace.certification_path(sample) == packaged
    assert data_workspace.LumiMask(data_workspace.certification_path(sample)).accepts(1, 5)
    sample.mkdir()
    override = sample / CERT
    override.write_text('{"2": [[1, 10]]}', encoding="utf-8")
    assert data_workspace.certification_path(sample) == override


def test_file_integrity_invalid_selection_and_upload_rollback(tmp_path, samples):
    workspace = DataWorkspace(tmp_path)
    with pytest.raises(ValueError):
        Selection(mass_low=120.0, mass_high=60.0)
    with pytest.raises(ValueError):
        Selection(min_pt=50.0, leading_pt=25.0)
    upload = workspace.import_begin(dict(name="bad.root", kind="data", size=4))["id"]
    with pytest.raises(ValueError, match="out-of-order"):
        workspace.import_chunk(dict(id=upload, offset=1, base64="cm9vdA=="))
    workspace.import_chunk(dict(id=upload, offset=0, base64="cm9vdA=="))
    with pytest.raises((OSError, ValueError)):
        workspace.import_finish(upload)
    assert not list((workspace.root / "datasets").glob("*.json"))
    workspace.load("cms-run2016g")
    with (samples / "run2016g-100k.root").open("ab") as file:
        file.write(b"changed")
    with pytest.raises(ValueError, match="checksum changed"):
        workspace.load("cms-run2016g")


def test_import_chunks_and_worker_allowlist_survive_restart(tmp_path, samples):
    handlers = operations(tmp_path)
    raw = (samples / "run2016g-100k.root").read_bytes()
    upload = handlers["data.import_begin"](
        config=dict(name="My data.root", kind="data", size=len(raw))
    )["id"]
    for offset in range(0, len(raw), 32768):
        handlers["data.import_chunk"](
            config=dict(
                id=upload,
                offset=offset,
                base64=base64.b64encode(raw[offset : offset + 32768]).decode(),
            )
        )
    item = handlers["data.import_finish"](upload_id=upload)
    assert item["id"].startswith("local-")
    assert operations(tmp_path)["data.load"](dataset_id=item["id"])["events"] == 5
    report = handlers["data.analyze"](config={"data_id": item["id"], "mc_id": None})
    assert report["populations"]["data"]["selected_events"] == 1


def test_saved_analysis_browser_survives_restart(tmp_path, samples):
    workspace = DataWorkspace(tmp_path)
    first = workspace.analyze({})
    second = workspace.analyze({"min_pt": 30.0, "leading_pt": 40.0})
    reopened = DataWorkspace(tmp_path)
    page = reopened.analyses()
    assert [item["id"] for item in page["items"]] == [second["id"], first["id"]]
    assert reopened.get(first["id"])["config"]["min_pt"] == 15
    assert reopened.reads == 0
    assert reopened.analyses(25)["items"] == []
    broken = reopened.root / "analyses" / ("a" * 24)
    broken.mkdir()
    (broken / "analysis.json").write_text("broken")
    assert reopened.analyses()["total"] == 2


def test_selected_real_event_display_survives_restart(tmp_path, samples):
    workspace = DataWorkspace(tmp_path)
    report = workspace.analyze({})
    reopened = DataWorkspace(tmp_path)
    event = reopened.event(report["id"], 0)
    assert event["mode"] == "cms"
    assert event["identity"]["event"] == "11"
    assert event["events"] == report["populations"]["data"]["selected_events"]
    assert len(event["tracks"]) == 2
    assert all(len(track["points"]) > 2 for track in event["tracks"])
    assert "no measured hits" in event["display"]
    reopened.event(report["id"], 0)
    assert reopened.reads == 1
    with pytest.raises(ValueError, match="out of range"):
        reopened.event(report["id"], event["events"])


def test_http_data_operations_need_token_for_analysis(tmp_path, samples):
    from fastapi.testclient import TestClient

    from heplab.server.app import create_app

    with TestClient(create_app(tmp_path / "artifacts"), base_url="http://127.0.0.1") as client:
        assert len(client.get("/api/v1/data/library").json()) == 2
        assert client.post("/api/v1/data/analyze", json={"config": {}}).status_code == 403
        token = client.app.state.jobs.token
        response = client.post(
            "/api/v1/data/analyze", json={"config": {}}, headers={"x-heplab-token": token}
        )
        assert response.status_code == 200
        assert response.json()["populations"]["data"]["selected_events"] == 1


def _write_display_sidecar(samples, event_offset=0):
    """Same layout as tools/build_cms_display_projection.py, for the 5 fixture events."""
    n = 5
    jagged = lambda rows: ak.Array(rows)  # noqa: E731
    collections = {
        "Jet": {
            "pt": [[60.0, 25.0]] * n, "eta": [[0.5, -1.8]] * n, "phi": [[1.0, -2.0]] * n,
            "mass": [[8.0, 4.0]] * n, "jetId": [[6, 2]] * n, "puId": [[7, 0]] * n,
            "btagDeepFlavB": [[0.9, 0.1]] * n, "chEmEF": [[0.1, 0.2]] * n,
            "neEmEF": [[0.2, 0.1]] * n, "chHEF": [[0.5, 0.4]] * n, "neHEF": [[0.2, 0.3]] * n,
        },
        "Electron": {
            "pt": [[20.0]] * n, "eta": [[0.3]] * n, "phi": [[2.5]] * n, "mass": [[0.0]] * n,
            "charge": [[-1]] * n, "cutBased": [[4]] * n, "pfRelIso03_all": [[0.02]] * n,
            "dxy": [[0.001]] * n, "dz": [[0.002]] * n,
        },
        "Photon": {"pt": [[]] * n, "eta": [[]] * n, "phi": [[]] * n, "cutBased": [[]] * n,
                   "pfRelIso03_all": [[]] * n},
        "Tau": {"pt": [[]] * n, "eta": [[]] * n, "phi": [[]] * n, "charge": [[]] * n,
                "decayMode": [[]] * n},
        "IsoTrack": {"pt": [[]] * n, "eta": [[]] * n, "phi": [[]] * n, "dz": [[]] * n},
        "Muon": {
            "dxy": [[0.0, 0.0]] * n, "dz": [[0.0, 0.0]] * n, "isGlobal": [[True, True]] * n,
            "isTracker": [[True, True]] * n, "isStandalone": [[True, True]] * n,
            "nStations": [[4, 3]] * n, "nTrackerLayers": [[12, 13]] * n, "ptErr": [[0.5, 0.6]] * n,
        },
    }  # fmt: skip
    with uproot.open(samples / "run2016g-100k.root") as base:
        ids = base["Events"].arrays(["run", "luminosityBlock", "event"], library="np")
    columns = {
        "run": ids["run"],
        "luminosityBlock": ids["luminosityBlock"],
        "event": ids["event"] + event_offset,
        **{name: np.full(n, value) for name, value in [
            ("MET_pt", 35.0), ("MET_phi", 0.5), ("MET_sumEt", 400.0), ("PuppiMET_pt", 30.0),
            ("PuppiMET_phi", 0.4), ("PV_x", 0.06), ("PV_y", 0.1), ("PV_z", -2.0),
            ("PV_npvs", 20), ("PV_npvsGood", 18)]},
    }  # fmt: skip
    for name, fields in collections.items():
        columns[name] = ak.zip({f: jagged(v) for f, v in fields.items()})
    output = samples / "run2016g-100k-display.root"
    with uproot.recreate(output) as sink:
        sink.mktree(
            "Events",
            {k: ak.Array(v).type for k, v in columns.items()},
            counter_name=lambda counted: "n" + counted,
            field_name=lambda outer, inner: inner if outer == "" else f"{outer}_{inner}",
        ).extend(columns)
    base_sha = json.loads((samples / "source.json").read_text())["derived_file_sha256"]
    (samples / "run2016g-100k-display.json").write_text(
        json.dumps(
            {
                "joins_sha256": base_sha,
                "derived_file_sha256": file_hash(output),
                "record": 1,
                "purpose": "event display only",
            }  # fmt: skip
        )
    )
    return output


def test_display_sidecar_adds_reconstructed_objects_by_identity(tmp_path, samples):
    _write_display_sidecar(samples)
    workspace = DataWorkspace(tmp_path)
    report = workspace.analyze({"mc_id": None})
    event = workspace.event(report["id"], 0)
    objects = event["objects"]
    assert event["objects_unavailable"] is None
    assert [jet["pt"] for jet in objects["jets"]] == [60.0, 25.0]
    assert objects["jets"][0]["em_fraction"] == pytest.approx(0.3)
    assert objects["met"]["pt"] == 35.0
    assert objects["vertex"]["position_m"] == pytest.approx([0.0006, 0.001, -0.02])
    assert [m["stations"] for m in objects["muon_quality"]] == [4, 3]
    path = objects["electrons"][0]["points"]
    assert len(path) > 2 and all(math.hypot(x, y) <= 1.29 and abs(z) <= 3.15 for x, y, z in path)
    assert "reconstructed" in event["display"]


def test_display_sidecar_missing_mismatched_or_changed_falls_back_to_muons(tmp_path, samples):
    workspace = DataWorkspace(tmp_path)
    report = workspace.analyze({"mc_id": None})
    event = workspace.event(report["id"], 0)
    assert event["objects"] is None and "no display sidecar" in event["objects_unavailable"]
    assert len(event["tracks"]) == 2

    _write_display_sidecar(samples, event_offset=1000)
    shifted = DataWorkspace(tmp_path).event(report["id"], 0)
    assert shifted["objects"] is None
    assert "identity does not match" in shifted["objects_unavailable"]

    output = _write_display_sidecar(samples)
    with output.open("ab") as file:
        file.write(b"changed")
    changed = DataWorkspace(tmp_path).event(report["id"], 0)
    assert changed["objects"] is None and "checksum changed" in changed["objects_unavailable"]
