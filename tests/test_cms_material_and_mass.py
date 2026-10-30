"""Material units, navigation failure handling and independent mass-model checks."""

import importlib.util
import math
from pathlib import Path

import pytest

from heplab.physics.cms_mass_calibration import (
    fit_template,
    heldout_closure,
    kernel,
    selected_pair,
)

spec = importlib.util.spec_from_file_location(
    "cms_geometry_worker", Path(__file__).parents[1] / "deploy/cms/geometry_worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class Material:
    def GetName(self):
        return "test-material"

    def GetDensity(self):
        return 2.329

    def GetRadLen(self):
        return 9.37

    def GetIntLen(self):
        return 46.5

    def IsMixture(self):
        return False

    def GetA(self):
        return 28.0855

    def GetZ(self):
        return 14


def test_material_density_and_cm_to_m_conversion_are_explicit():
    record = worker.material_record(Material())
    assert record["density_g_cm3"] == 2.329
    assert record["radiation_length_m"] == pytest.approx(0.0937)
    assert record["interaction_length_m"] == pytest.approx(0.465)
    assert record["elements"][0]["mass_fraction"] == 1
    broken = Material()
    broken.GetRadLen = lambda: 0
    with pytest.raises(ValueError, match="radiation/interaction"):
        worker.material_record(broken)
    broken.GetDensity = lambda: 0
    assert worker.material_record(broken)["radiation_length_m"] is None


def test_rounded_cms_mixture_fractions_are_audited_and_normalized():
    class Mixture(Material):
        def IsMixture(self):
            return True

        def GetNelements(self):
            return 2

        def GetAmixt(self):
            return [12.0, 16.0]

        def GetZmixt(self):
            return [6.0, 8.0]

        def GetWmixt(self):
            return [0.500025, 0.500025]

    record = worker.material_record(Mixture())
    assert record["source_mass_fraction_sum"] == pytest.approx(1.00005)
    assert sum(element["mass_fraction"] for element in record["elements"]) == pytest.approx(1)
    assert [element["mass_fraction"] for element in record["elements"]] == pytest.approx([0.5, 0.5])

    class InvalidMixture(Mixture):
        def GetWmixt(self):
            return [0.505, 0.505]

    with pytest.raises(ValueError, match="fractions do not sum"):
        worker.material_record(InvalidMixture())


def test_stalled_navigation_fails_instead_of_skipping_a_thin_layer():
    class Stalled:
        def InitTrack(self, *args):
            return self

        def IsOutside(self):
            return False

        def GetCurrentNode(self):
            return self

        def GetVolume(self):
            return self

        def GetMaterial(self):
            return Material()

        def GetPath(self):
            return "/stalled"

        def FindNextBoundaryAndStep(self, *args):
            return self

        def GetStep(self):
            return 0

    with pytest.raises(ValueError, match="stalled"):
        worker.trace_ray(Stalled(), [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1.0)


def test_pair_ranking_never_selects_by_closeness_to_the_z_mass():
    event = {
        "Muon_pt": [50.0, 45.0, 80.0],
        "Muon_eta": [0.0, 0.0, 0.0],
        "Muon_phi": [0.0, math.pi, math.pi],
        "Muon_mass": [0.105] * 3,
        "Muon_charge": [-1, 1, 1],
        "Muon_tightId": [True] * 3,
        "Muon_pfRelIso04_all": [0.05] * 3,
    }
    pair = selected_pair(event)
    assert pair["muons"][1]["pt"] == 80
    assert pair["mass_gev"] > 120  # nearest-Z pair would have been ~95 GeV


def test_integrated_template_matches_an_independent_gaussian_cdf():
    np = pytest.importorskip("numpy")
    scipy = pytest.importorskip("scipy.special")
    edges = np.array([75.0, 85.0, 90.0, 95.0, 105.0])
    actual, _, _ = kernel([91.0] * 100, edges, [1, 0.01, 0.1])
    expected = np.diff(scipy.ndtr((edges - 91) / 0.91))
    expected = 0.9 * expected / expected.sum() + 0.1 * np.diff(edges) / 30
    assert np.allclose(actual, expected, rtol=1e-13, atol=1e-14)
    assert actual.sum() == pytest.approx(1)
    with pytest.raises(ValueError):
        kernel([91.0] * 100, edges, [1, 0, 0])


def test_template_fit_recovers_a_separately_generated_mass_scale():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    rng = np.random.default_rng(1984)
    mc = rng.normal(91.2, 2.0, 8000)
    independent = rng.normal(91.2, 2.0, 8000)
    observed = 1.003 * independent + rng.normal(0, 0.012 * independent)
    fitted = fit_template(observed, mc, np.linspace(75, 105, 31))
    assert fitted["mass_scale"] == pytest.approx(1.003, abs=0.0015)
    assert fitted["additional_fractional_mass_sigma"] == pytest.approx(0.012, abs=0.006)
    assert "not per-muon" in fitted["scope"]


def test_heldout_statistic_preserves_normalization_and_mc_covariance():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    rng = np.random.default_rng(828)
    result = heldout_closure(
        rng.uniform(75, 105, 5000),
        rng.uniform(74, 106, 6000),
        np.linspace(75, 105, 31),
        [1, 0.005, 0],
    )
    assert sum(result["expected"]) == pytest.approx(sum(result["observed"]))
    assert result["degrees_of_freedom"] == 29
    assert 0 <= result["pvalue"] <= 1
    assert "finite held-out MC template" in result["covariance_includes"]
    assert "physics systematics" in result["covariance_omits"]
