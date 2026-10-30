"""Versioned, fail-closed descriptions of scientific model scope."""

from __future__ import annotations

from .constants import constants_record

MODEL_SPEC_SCHEMA = "heplab-model-spec-v1"

_COMPONENTS = {
    "declared-muon-pair-v1": {
        "name": "Declared back-to-back muon test pair",
        "units": {"momentum": "GeV/c", "mass": "GeV/c^2", "charge": "e"},
        "domain": {"momentum_gev_c": [1.0, 100.0], "particle": "muon"},
        "assumptions": ["declared test fixture; no collision generation"],
        "omitted_effects": ["collision production", "cosmic-ray production"],
        "evidence": {"state": "analytic_kinematics_checked", "scope": "fixture kinematics"},
        "references": ["PDG R1"],
    },
    "angular-muon-sample-v1": {
        "name": "Address-seeded angular muon test sample",
        "units": {"momentum": "GeV/c", "eta": "1", "phi": "rad"},
        "domain": {"momentum_gev_c": [1.0, 100.0], "abs_eta": [0.0, 2.4]},
        "assumptions": ["fixed momentum and back-to-back charges", "no collisions"],
        "omitted_effects": ["collision production", "cosmic-ray production"],
        "evidence": {"state": "educational_unvalidated", "scope": "toy source distribution"},
        "references": [],
    },
    "ideal-solenoid-helix-v1": {
        "name": "Uniform axial-field vacuum helix",
        "units": {"position": "m", "momentum": "GeV/c", "field": "T", "time": "ns"},
        "domain": {"field": "uniform axial Bz", "path_length_m": [0.0, 20.0]},
        "assumptions": ["fixed momentum", "vacuum", "no electric field"],
        "omitted_effects": ["material", "decay", "field fringe", "radiation", "spin"],
        "evidence": {"state": "analytic_reference_checked", "scope": "closed-form helix"},
        "references": [],
    },
    "cms-tracker-oae-3.8t-v1": {
        "name": "Pinned CMS tracker OAE field reference",
        "units": {"position": "m", "momentum": "GeV/c", "field": "T", "time": "ns"},
        "domain": {"field_tesla": 3.8, "radius_m": [0.0, 1.15], "abs_z_m": [0.0, 2.8]},
        "assumptions": ["vacuum Lorentz ODE", "classical RK4", "nominal parametrization"],
        "omitted_effects": ["run-era IOV", "full field map", "material navigation", "decay"],
        "evidence": {
            "state": "pinned_software_reference_regression",
            "scope": "field-vector port only",
        },
        "references": ["CMSSW c04fa510"],
    },
    "pdg-si-muon-loglinear-split-v1": {
        "name": "Muon mean ionization in silicon",
        "units": {"kinetic_energy": "GeV", "stopping_power": "GeV/m", "thickness": "m"},
        "domain": {"kinetic_energy_gev": [0.1, 100.0], "material": "silicon", "particle": "muon"},
        "assumptions": ["continuous mean energy loss", "log-energy interpolation"],
        "omitted_effects": [
            "straggling",
            "delta rays",
            "secondary production",
            "detector calibration",
        ],
        "evidence": {"state": "heldout_named_reference_table_agreement", "scope": "PDG mean table"},
        "references": ["PDG R3"],
    },
    "thin-slab-highland-v1": {
        "name": "Single homogeneous slab with Highland Gaussian core",
        "units": {"thickness": "m", "radiation_length": "m", "angle": "rad", "deposit": "GeV"},
        "domain": {
            "mass_gev": [0.1, "particle-dependent"],
            "abs_charge_e": 1,
            "fractional_loss_max": 0.1,
            "x_over_x0": [0.001, 0.1],
        },
        "assumptions": [
            "continuous mean loss",
            "small-angle Gaussian core",
            "untracked medium recoil",
        ],
        "omitted_effects": [
            "energy-loss straggling",
            "Moliere tails",
            "secondaries",
            "geometry navigation",
        ],
        "evidence": {"state": "educational_unvalidated", "scope": "bounded single-slab arithmetic"},
        "references": ["PDG R2"],
    },
    "deposit-electronics-v1": {
        "name": "Illustrative channel digitization",
        "units": {"deposit": "GeV", "signal": "ADC"},
        "domain": {
            "gain_adc_per_gev": "configured",
            "threshold_adc": "configured",
            "saturation_adc": "configured",
        },
        "assumptions": ["explicit gain, pedestal, Gaussian noise, threshold and clipping"],
        "omitted_effects": ["CMS front-end calibration", "channel response and occupancy"],
        "evidence": {"state": "educational_unvalidated", "scope": "arithmetic only"},
        "references": [],
    },
    "delphes-reference-response-v1": {
        "name": "Truth-to-object DY/DELPHES reference response",
        "units": {"momentum": "GeV/c", "eta": "1", "efficiency": "1"},
        "domain": {"pt_gev_c": [5.0, 200.0], "abs_eta": [0.0, 2.4], "pileup": False},
        "assumptions": ["eta-bin aggregate transfer from a pinned DY sample"],
        "omitted_effects": ["pT-local validation", "non-DY processes", "CMS data calibration"],
        "evidence": {"state": "scoped_generator_card_transfer", "scope": "fixed DY/DELPHES sample"},
        "references": ["DELPHES R9", "PYTHIA R10"],
    },
    "pythia8-delphes-dy-v1": {
        "name": "PYTHIA8 Drell-Yan plus DELPHES CMS-card chain",
        "units": {"beam_energy": "GeV", "mass": "GeV/c^2", "cross_section": "pb"},
        "domain": {"sqrt_s_tev": [1.0, 14.0], "hard_mass_gev": [60.0, 120.0], "pileup": False},
        "assumptions": ["fixed tune and PDF settings", "fast detector response"],
        "omitted_effects": ["Geant4 transport", "CMS conditions and calibration"],
        "evidence": {"state": "generator_card_regression", "scope": "pinned DY workflow"},
        "references": ["PYTHIA R10", "DELPHES R9"],
    },
    "recorded-nanoaod-ideal-display-v1": {
        "name": "Recorded NanoAOD muon with an IP-assumed ideal-field display path",
        "units": {"momentum": "GeV/c", "position": "m", "field": "T"},
        "domain": {"source": "recorded NanoAOD reconstructed muon", "display_field_t": 3.8},
        "assumptions": [
            "display origin is assumed to be the interaction point",
            "uniform ideal solenoid is used only to draw a path",
        ],
        "omitted_effects": [
            "measured track parameters",
            "hit-level reconstruction",
            "run-era field",
            "material transport",
        ],
        "evidence": {
            "state": "display_only_no_reconstruction_claim",
            "scope": "illustration of a recorded muon direction",
        },
        "references": [],
    },
}


def registered_model_ids() -> frozenset[str]:
    return frozenset(_COMPONENTS)


def model_spec_for_run(config) -> dict:
    """Create an explicit model envelope for an analytic or collision run."""
    values = config.model_dump() if hasattr(config, "model_dump") else dict(config)
    if values.get("mode") == "pythia":
        requested = ["pythia8-delphes-dy-v1", "ideal-solenoid-helix-v1"]
    else:
        source = (
            "angular-muon-sample-v1"
            if values.get("source_model") == "angular_sample"
            else "declared-muon-pair-v1"
        )
        field = (
            "cms-tracker-oae-3.8t-v1"
            if values.get("field_model") == "cms_tracker"
            else "ideal-solenoid-helix-v1"
        )
        requested = [
            source,
            field,
            "pdg-si-muon-loglinear-split-v1",
            "thin-slab-highland-v1",
            "deposit-electronics-v1",
        ]
        if values.get("response_model") == "delphes_reference":
            requested.append("delphes-reference-response-v1")
    if any(model_id not in _COMPONENTS for model_id in requested):
        raise ValueError("unknown model ID; no model specification is registered")
    components = [{"id": model_id, "version": 1, **_COMPONENTS[model_id]} for model_id in requested]
    return {
        "schema": MODEL_SPEC_SCHEMA,
        "components": components,
        "constants": constants_record(),
        "configuration": values,
        "overall_status": "not_a_global_validation_claim",
        "limitations": [
            "model components have distinct domains and evidence states",
            "a successful run does not establish detector calibration or physics validation",
        ],
    }


def display_model_spec(model_id: str = "recorded-nanoaod-ideal-display-v1") -> dict:
    """Return a fail-closed specification for a reconstructed-object display path."""
    if model_id not in _COMPONENTS:
        raise ValueError("unknown display model ID; no model specification is registered")
    return {
        "schema": MODEL_SPEC_SCHEMA,
        "components": [{"id": model_id, "version": 1, **_COMPONENTS[model_id]}],
        "constants": constants_record(),
        "overall_status": "display_only_not_a_measurement_or_reconstruction",
        "limitations": ["the displayed path is not a fitted track or measured hit"],
    }
