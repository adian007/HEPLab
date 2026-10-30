"""CMS-referenced resonance closure and eta-binned resolution regressions."""

import hashlib
import json
import math

import pytest
from tools.build_cms_resonance_validation import report_from_rows

from heplab.analyses.dimuon.run import invariant_mass
from heplab.physics.calibration import REFERENCE

REFERENCE_FILE = REFERENCE / "cms-resonance-validation.json"


def test_z_jpsi_and_upsilon_peaks_close_on_cms_reference_masses():
    reference = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    muon_mass = 0.1056583755
    for name, target in reference["resonance_masses_gev"].items():
        momentum = math.sqrt((target["mass"] / 2) ** 2 - muon_mass**2)
        first = {"pt": momentum, "eta": 0.0, "phi": 0.0, "mass": muon_mass}
        second = {
            "pt": momentum,
            "eta": 0.0,
            "phi": math.pi,
            "mass": muon_mass,
        }
        assert invariant_mass(first, second) == pytest.approx(
            target["mass"], abs=target["tolerance"]
        ), name


def test_frozen_cms_data_fits_and_heldout_z_template_closure_pass():
    pairs_path = REFERENCE / "cms-resonance-selected-pairs.json"
    report_path = REFERENCE / "cms-resonance-data-report.json"
    rows = json.loads(pairs_path.read_text(encoding="utf-8"))
    frozen_report = json.loads(report_path.read_text(encoding="utf-8"))
    provenance = frozen_report["source"]
    assert (
        hashlib.sha256(pairs_path.read_bytes()).hexdigest() == provenance["selected_pairs_sha256"]
    )
    assert provenance["record"] == 30522
    assert provenance["entry_start"] == 0
    assert provenance["entry_stop"] == 100_000
    assert provenance["source_integrity"]["verified"] is True
    assert provenance["certification_sha256"]

    # Refit from the frozen candidate sample: CI does not rely on stored fit results.
    report = report_from_rows(rows, provenance)
    assert report["passed"] is True
    assert report["deterministic_result_sha256"] == frozen_report["deterministic_result_sha256"]
    assert report["z_dimuon"]["passed"] is True
    assert report["z_dimuon"]["heldout_template_closure"]["pvalue"] >= 0.01
    for name in ("jpsi", "upsilon_1s", "upsilon_2s", "upsilon_3s"):
        assert report["fits"][name]["reference_gate"]["passed"] is True

    resolution = report["jpsi_resolution_by_abs_eta"]
    assert len(resolution) == 3
    assert all(row["passed"] for row in resolution)
    widths = [row["fit"]["sigma_gev"] for row in resolution]
    assert widths[0] < widths[1] < widths[2]


def test_upsilon_reference_distinguishes_three_central_peaks():
    reference = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    peaks = reference["resonance_masses_gev"]
    resolution = reference["upsilon_published_resolution_gev"]
    central = resolution["central_rapidity"]
    inclusive = resolution["all_rapidities"]
    assert central == pytest.approx(0.069)
    assert inclusive == pytest.approx(0.096)
    masses = [peaks[name]["mass"] for name in ("upsilon_1s", "upsilon_2s", "upsilon_3s")]
    for first, second in zip(masses, masses[1:], strict=False):
        assert second - first > 3 * central
