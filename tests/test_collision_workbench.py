"""Collision analysis and automatic runtime discovery contracts."""

import json
import math
import subprocess

import pytest

pytest.importorskip("pydantic", minversion="2")

from heplab.analyses.collision import analyze  # noqa: E402
from heplab.server.workbench import RunConfig  # noqa: E402
from heplab.sim import pipeline  # noqa: E402


def muon(identity, pt=45.0, charge=-1, phi=0.0, iso=0.1):
    return dict(object_id=identity, pt=pt, charge=charge, phi=phi, eta=0.0, mass=0.105658, iso=iso)


def event(weight=1.0, muons=None):
    return {
        "EventInfo": {"weight": weight},
        "Muon": muons if muons is not None else [muon(0), muon(1, charge=1, phi=math.pi)],
        "Jet": [],
        "MET": {"pt": 5.0},
    }


def test_signed_weights_and_per_event_correlated_muon_uncertainties():
    result = analyze(
        [event(2.0), event(-0.5), event(1.0, [])], RunConfig(mode="pythia", backend="delphes")
    )
    assert result["events"] == 3 and result["selected_events"] == 2
    assert result["cutflow"][0]["sumw"] == 2.5
    assert result["cutflow"][-1]["sumw"] == 1.5
    assert result["cutflow"][-1]["sumw2"] == 4.25
    mass = result["histograms"]["mass"]
    assert sum(mass["sumw_with_flow"]) == pytest.approx(1.5)
    assert sum(mass["sumw2_with_flow"]) == pytest.approx(4.25)
    pt = result["histograms"]["pt"]
    assert sum(pt["sumw_with_flow"]) == pytest.approx(3.0)
    assert sum(pt["sumw2_with_flow"]) == pytest.approx(8.5)
    assert sum(pt["event_sumw2_with_flow"]) == pytest.approx(17.0)
    assert result["event_rows"][2]["selected"] is False


def test_pair_rank_is_not_biased_towards_the_mass_window():
    row = event(muons=[muon(0, 70, 1), muon(1, 70, -1, math.pi), muon(2, 30, -1, math.pi)])
    result = analyze([row], RunConfig(mode="pythia", backend="delphes"))
    assert result["selected_events"] == 0
    assert result["event_rows"][0]["pair_ids"] == [0, 1]
    assert result["event_rows"][0]["mass_gev"] > 120
    assert result["histograms"]["mass"]["sumw_with_flow"][-1] == 1.0


def test_missing_measurements_are_not_replaced_with_fake_zeros():
    absent = event()
    absent["Muon"] = None
    with pytest.raises(ValueError, match="Muon collection"):
        analyze([absent], RunConfig())
    absent = event()
    absent["MET"]["pt"] = None
    absent["Muon"][0]["iso"] = None
    result = analyze([absent], RunConfig())
    assert result["selected_events"] == 0
    assert sum(result["histograms"]["met"]["entries_with_flow"]) == 0
    assert result["event_rows"][0]["met_gev"] is None


def test_collision_cuts_change_the_selected_population_and_reject_bad_windows():
    result = analyze([event()], RunConfig(muon_pt_min_gev=50.0))
    assert result["selected_events"] == 0
    assert result["cutflow"][0]["events"] == 1 and result["cutflow"][1]["events"] == 0
    with pytest.raises(ValueError, match="increasing"):
        RunConfig(mass_min_gev=100.0, mass_max_gev=90.0)


def test_wsl_discovery_decodes_windows_output_and_ignores_docker(monkeypatch):
    calls = []

    def run(command, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        calls.append(command)
        if "--list" in command:
            return subprocess.CompletedProcess(
                command, 0, "docker-desktop\r\nUbuntu\r\n".encode("utf-16-le")
            )
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"prefix": "/home/test/.cache/heplab/sim-runtime", "distro": "Ubuntu"}),
        )

    monkeypatch.setattr(pipeline.subprocess, "run", run)
    assert pipeline._discover_wsl_runtime() == ("/home/test/.cache/heplab/sim-runtime", "Ubuntu")
    assert len(calls) == 2 and calls[1][2] == "Ubuntu"
    assert all("shell" not in call for call in calls)


def test_simulation_children_cannot_consume_desktop_ipc_requests():
    assert pipeline._process_options()["stdin"] == subprocess.DEVNULL


def test_slow_wsl_is_not_reported_as_a_missing_installation(monkeypatch):
    def run(command, **kwargs):
        if "--list" in command:
            return subprocess.CompletedProcess(command, 0, b"Ubuntu\n")
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(pipeline.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="WSL runtime check timed out"):
        pipeline._discover_wsl_runtime()


def test_cold_wsl_metadata_timeout_is_retried_once(monkeypatch):
    calls = []

    def run(command, **kwargs):
        assert kwargs["stdin"] == subprocess.DEVNULL
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, "inventory")

    monkeypatch.setattr(pipeline.subprocess, "run", run)
    assert pipeline._wsl_file("Ubuntu", "/runtime/inventory") == "inventory"
    assert len(calls) == 2

    def always_timeout(command, **kwargs):
        calls.append(command)
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(pipeline.subprocess, "run", always_timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        pipeline._wsl_file("Ubuntu", "/runtime/inventory")
    assert len(calls) == 4


def test_explicit_runtime_configuration_is_preserved(tmp_path, monkeypatch):
    (tmp_path / "heplab-runtime.json").write_text(
        json.dumps({"versions": pipeline.VERSIONS, "explicit_lock_sha256": "fixture"})
    )
    monkeypatch.setenv("HEPLAB_SIM_PREFIX", str(tmp_path))
    monkeypatch.delenv("HEPLAB_SIM_WSL_DISTRO", raising=False)
    monkeypatch.setattr(pipeline.importlib.util, "find_spec", lambda _name: object())

    def forbidden():
        raise AssertionError("explicit config must not probe WSL")

    monkeypatch.setattr(pipeline, "_discover_runtime", forbidden)
    assert pipeline.runtime()["prefix"] == str(tmp_path)
