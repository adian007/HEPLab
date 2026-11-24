"""Portable offline practice workflow shared by the Workbench and Jupyter."""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import version
from math import isclose
from pathlib import Path

from .. import fit_peak, load, run
from ..io.provenance import config_hash
from . import PRACTICE_SOURCE, practice_events, start

PRESET_SCHEMA = "heplab-lab-preset-v1"
RESULT_SCHEMA = "heplab-z-boson-result-v1"
SCOPE = "Synthetic teaching sample · no CMS collision data or detector calibration"


def _validate_preset(preset: dict, revision: int) -> None:
    if (
        not isinstance(preset, dict)
        or type(preset.get("revision")) is not int
        or preset != {"schema": PRESET_SCHEMA, "lab": "z-boson", "revision": revision}
    ):
        raise ValueError("Choose a supported Rediscover the Z boson preset.")


def preview(preset: dict) -> dict:
    """Resolve a file to the bundled lab and return the event used in the mass exercise."""
    lab = start()
    spec = lab.spec["workbench"]
    _validate_preset(preset, spec["revision"])
    event = practice_events(1, seed=spec["seed"])[0]
    return {
        "scope": SCOPE,
        "source": PRACTICE_SOURCE,
        "settings": spec,
        "event": event["EventInfo"]["event"],
        "muons": event["Muon"][:2],
        "steps": lab.steps,
    }


def analyze(
    preset: dict,
    *,
    min_pt_gev: float,
    max_rel_iso: float,
    require_opposite_charge: bool,
    mass_gev: float | None = None,
    width_answer: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Execute the offline lab and produce a portable artifact with its teaching feedback."""
    lab = start()
    spec = lab.spec["workbench"]
    _validate_preset(preset, spec["revision"])
    count, seed = spec["event_count"], spec["seed"]
    events = practice_events(count, seed=seed)
    config = {
        "selection": {
            "muons": {"min_pt": min_pt_gev, "max_rel_iso": max_rel_iso, "max_abs_eta": 2.4},
            "pairs": {
                "require_opposite_charge": require_opposite_charge,
                "mass_window": [0.5, 200.0],
            },
        },
        "binning": {"dimuon_mass": {"range": [0.5, 200.0], "bins": 133}},
        "candidate_policy": "all_pairs",
        "validation": {"mode": "educational"},
    }
    lab.check("load", events)
    lab.check("select", config)
    if mass_gev is not None:
        lab.check("mass", mass_gev)
    if width_answer:
        lab.check("width", width_answer)

    def tracked_events():
        for index, event in enumerate(events):
            if progress and index % 128 == 0:
                progress(index, count)
            yield event
        if progress:
            progress(count, count)

    result = run(tracked_events(), config=config)
    lab.check("histogram", result)
    window = tuple(spec["fit_window_gev"])
    fit = None
    fit_error = None
    try:
        fit = fit_peak(result, window=window)
        config_hash(fit)
    except ValueError as exc:
        fit, fit_error = None, str(exc)
    if fit is not None:
        lab.check("fit", fit)
    else:
        lab.check("fit", {"success": False})
    artifact = {
        "schema": RESULT_SCHEMA,
        "mode": "z-boson",
        "scope": SCOPE,
        "preset": preset,
        "sample": {"generator": PRACTICE_SOURCE, "seed": seed, "event_count": count},
        "analysis_config": config,
        "analysis": result,
        "fit_window_gev": list(window),
        "fit": fit,
        "fit_error": fit_error,
        "fit_environment": {name: version(name) for name in ("iminuit", "numpy", "scipy")},
        "progress": lab.progress(),
    }
    artifact["payload_content_sha256"] = config_hash(artifact)
    return artifact


def reopen(path: str | Path) -> dict:
    """Verify a Workbench lab artifact before using it as a replay input."""
    artifact = load(path)
    if artifact.get("schema") != RESULT_SCHEMA or not artifact.get("payload_content_sha256"):
        raise ValueError("Expected a checksummed HEPLab Z-boson lab result.")
    spec = start().spec["workbench"]
    _validate_preset(artifact.get("preset"), spec["revision"])
    sample = {
        "generator": PRACTICE_SOURCE,
        "seed": spec["seed"],
        "event_count": spec["event_count"],
    }
    if artifact.get("sample") != sample:
        raise ValueError("This offline practice sample is unsupported.")
    return artifact


def reproduce(artifact: dict) -> tuple[list[dict], dict]:
    """Recompute counts and, for a converged fit, check the mean and uncertainty."""
    sample = artifact["sample"]
    events = practice_events(sample["event_count"], seed=sample["seed"])
    result = run(events, config=artifact["analysis_config"])
    saved = artifact["analysis"]
    if result["cutflow"] != saved["cutflow"] or result["histogram"] != saved["histogram"]:
        raise ValueError("The replay did not reproduce the saved cutflow and mass histogram.")
    fit = artifact["fit"]
    if fit and fit["success"]:
        replay = fit_peak(result, window=tuple(artifact["fit_window_gev"]))
        if not replay["success"] or any(
            not isclose(replay[field]["mean"], fit[field]["mean"], rel_tol=0, abs_tol=0.005)
            for field in ("values", "errors")
        ):
            raise ValueError("The replay did not reproduce the fitted mean and error to 0.005 GeV.")
    return events, result
