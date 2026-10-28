"""Generator contract checks using native ROOT fixtures; not generator validation."""

import math

import pytest

from heplab.sim.pipeline import inspect_root, normalization, settings


def test_generator_normalization_units_and_incomplete_population():
    log = "| sum | 400 100 100 | 1.3e-06 8e-08 |"
    value = normalization(log, 100)
    assert value["cross_section_pb"] == pytest.approx(1300)
    assert value["cross_section_error_pb"] == pytest.approx(80)
    for text, count in (
        (log, 101),
        (log + log, 100),
        ("no statistics", 100),
        ("| sum | 1 2 2 | 1e-6 1e-8 |", 2),
    ):
        with pytest.raises(ValueError):
            normalization(text, count)


@pytest.mark.parametrize(
    "params",
    [
        {"events": 0},
        {"events": True},
        {"seed": 0},
        {"seed": 900000001},
        {"energy_gev": math.nan},
        {"energy_gev": 999},
    ],
)
def test_generator_invalid_settings(params):
    with pytest.raises(ValueError):
        settings(**params)


def test_registered_process_freezes_beams_decays_tune_pdf_and_seed():
    config = settings(events=3, seed=17)
    for line in (
        "Main:numberOfEvents = 3",
        "Random:seed = 17",
        "Beams:eCM = 13000",
        "Tune:pp = 14",
        "PDF:pSet = 13",
        "23:onIfAny = 13",
    ):
        assert line in config


def test_root_inspection_rejects_partial_and_missing_truth_preserves_signed_weights(tmp_path):
    ak = pytest.importorskip("awkward")
    uproot = pytest.importorskip("uproot")
    path = tmp_path / "events.root"
    branches = {
        "Particle." + key: ak.Array([[1], [1]])
        for key in ("PID", "Status", "M1", "M2", "D1", "D2", "E", "Px", "Py", "Pz")
    }
    for key in ("PID", "Status", "E", "Px", "Py", "Pz"):
        values = {
            "PID": [2212, 2212, 13, -13],
            "Status": [4, 4, 1, 1],
            "E": [6500.0, 6500.0, 6500.0, 6500.0],
            "Px": [0.0, 0.0, 6500.0, -6500.0],
            "Py": [0.0, 0.0, 0.0, 0.0],
            "Pz": [6500.0, -6500.0, 0.0, 0.0],
        }[key]
        branches["Particle." + key] = ak.Array([values, values])
    branches["Event.Weight"] = ak.Array([[2.0], [-0.5]])
    with uproot.recreate(path) as root:
        root.mktree("Delphes", branches)
    value = inspect_root(path, 2)
    assert value["sumw"] == 1.5
    assert value["sumw2"] == 4.25
    assert value["negative_sumw"] == -0.5
    with pytest.raises(ValueError, match="incomplete"):
        inspect_root(path, 3)
    with uproot.recreate(path) as root:
        root.mktree("Delphes", {"Event.Weight": ak.Array([[1.0]])})
    with pytest.raises(ValueError, match="truth"):
        inspect_root(path, 1)
