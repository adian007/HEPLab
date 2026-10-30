"""CMS-referenced resonance closure and eta-binned resolution regressions."""

import hashlib
import json
import math

import pytest
from tools.build_cms_resonance_validation import report_from_rows

from heplab.analyses.dimuon.run import invariant_mass
from heplab.physics.calibration import REFERENCE
from heplab.physics.cms_resonance_validation import event_split, select_candidate_index

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


def test_frozen_cms_data_fit_reports_predeclared_gates_without_relabeling_failures():
    pairs_path = REFERENCE / "cms-resonance-selected-pairs-v2.json"
    report_path = REFERENCE / "cms-resonance-data-report-v2.json"
    rows = json.loads(pairs_path.read_text(encoding="utf-8"))
    frozen_report = json.loads(report_path.read_text(encoding="utf-8"))
    provenance = frozen_report["source"]
    assert (
        hashlib.sha256(pairs_path.read_bytes()).hexdigest() == provenance["selected_pairs_sha256"]
    )
    assert provenance["record"] == 30522
    assert provenance["entry_start"] >= 100_000
    assert provenance["entry_stop"] > provenance["entry_start"]
    assert provenance["source_integrity"]["verified"] is True
    assert provenance["certification_sha256"]
    assert frozen_report["schema"] == "heplab-cms-data-resonance-validation-v2"
    assert frozen_report["selection"]["candidate"].find("mass is not used") >= 0
    assert frozen_report["selection"]["split"]["selection_and_split_precede_mass_fit"] is True
    assert frozen_report["validation_level"] == "named_reference_data_regression"
    assert "not an independent dataset" in frozen_report["limits"][0]

    # Refit from the frozen candidate sample: CI does not rely on stored fit results.
    report = report_from_rows(rows, provenance)
    assert report["deterministic_result_sha256"] == frozen_report["deterministic_result_sha256"]
    assert report["z_dimuon"]["passed"] is True
    assert report["z_dimuon"]["heldout_template_closure"]["pvalue"] >= 0.01
    for name in ("jpsi", "upsilon_1s", "upsilon_2s", "upsilon_3s"):
        assert report["fits"][name]["heldout_fit"]["entries"] >= 40
        assert "heldout_reference_gate" in report["fits"][name]
    # The frozen Υ(2S) held-out mass misses the declared 30 MeV tolerance.
    # Preserve the failed result; do not relax the gate to turn this into a pass.
    assert report["fits"]["upsilon_2s"]["heldout_reference_gate"]["passed"] is False
    assert report["passed"] is False

    resolution = report["jpsi_resolution_by_abs_eta"]
    assert len(resolution) == 3
    assert all(row["passed"] for row in resolution)
    widths = [row["fit"]["sigma_gev"] for row in resolution]
    assert all(math.isfinite(width) and width > 0 for width in widths)


def test_low_mass_candidate_choice_uses_only_scalar_pt_sum():
    # Swapping pair masses while preserving pT ordering cannot change the choice;
    # mass and reference targets are not accepted by the selector API.
    assert select_candidate_index([(4.0, 5.0), (8.0, 3.0), (2.0, 2.0)]) == 1
    assert select_candidate_index([(4.0, 5.0), (8.0, 3.0), (2.0, 2.0)]) == 1
    assert select_candidate_index([(4.0, 5.0), (4.0, 5.0)]) == 0
    assert select_candidate_index([]) is None
    with pytest.raises(ValueError):
        select_candidate_index([(1.0, float("nan"))])


def test_resonance_event_split_is_deterministic_and_event_disjoint():
    identities = [(278822, 1122, number) for number in range(1000)]
    assignments = {identity: event_split(*identity) for identity in identities}
    assert assignments == {identity: event_split(*identity) for identity in identities}
    training = {identity for identity, split in assignments.items() if split == "training"}
    heldout = {identity for identity, split in assignments.items() if split == "heldout"}
    assert training.isdisjoint(heldout)
    assert 150 <= len(heldout) <= 250


def test_legacy_target_selected_report_is_not_independent_evidence():
    legacy_path = REFERENCE / "cms-resonance-data-report-target-dependent-legacy.json"
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert legacy["status"] == "exploratory_target_dependent"
    assert legacy["passed"] is False
    assert legacy["independent_validation_eligible"] is False


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
