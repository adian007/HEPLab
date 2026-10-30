"""Fit and hold out a measured 1D CMS mass template; never tune transport from it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import uproot

from heplab.physics.cms_mass_calibration import (
    bootstrap_template,
    fit_template,
    heldout_closure,
    selected_pair,
)

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "artifacts/cms/measured"
    measured_report = json.loads((folder / "validation.json").read_text(encoding="utf8"))
    selected = folder / "selected-pairs.json"
    if (
        hashlib.sha256(selected.read_bytes()).hexdigest()
        != measured_report["selected_pairs_sha256"]
    ):
        raise ValueError("measured pair sample changed")
    data = json.loads(selected.read_text(encoding="utf8"))
    data_masses = [[row["mass_gev"] for row in data if row["split"] == split] for split in (0, 1)]
    source = json.loads((folder / "dy-source.json").read_text(encoding="utf8"))
    mc_file = folder / "dy-ul16-100k.root"
    if hashlib.sha256(mc_file.read_bytes()).hexdigest() != source["derived_file_sha256"]:
        raise ValueError("MC sample changed")
    with uproot.open(mc_file) as root:
        events = root["Events"].arrays(source["branches"])
    mc_masses: list[list[float]] = [[], []]
    seen = set()
    for event in events:
        if float(event["genWeight"]) != 1:
            raise ValueError("this exploratory template requires unit-weight LO MC")
        identity = tuple(int(event[key]) for key in ("run", "luminosityBlock", "event"))
        if identity in seen:
            raise ValueError("duplicate MC event identity")
        seen.add(identity)
        if not (
            bool(event["HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ"])
            or bool(event["HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ"])
        ):
            continue
        pair = selected_pair(event)
        if pair is None or not 60 <= pair["mass_gev"] < 120:
            continue
        split = (
            hashlib.sha256(("cms-dy-mass-v1:" + ":".join(map(str, identity))).encode()).digest()[0]
            & 1
        )
        mc_masses[split].append(pair["mass_gev"])
    edges = np.linspace(75, 105, 31)
    z_input_fixture = {
        "schema": "heplab-cms-z-template-input-v1",
        "data_source": {
            "record": measured_report["data_record"],
            "selected_pairs_sha256": measured_report["selected_pairs_sha256"],
            "entries": measured_report["data_source"]["entry_stop"],
            "split": measured_report["split"],
        },
        "mc_source": source,
        "fit_edges_gev": edges.tolist(),
        "data_masses_gev": data_masses,
        "mc_masses_gev": mc_masses,
    }
    z_input_fixture["sha256"] = hashlib.sha256(
        json.dumps(z_input_fixture, sort_keys=True, separators=(",", ":")).encode("utf8")
    ).hexdigest()
    fit = fit_template(data_masses[0], mc_masses[0], edges)
    bootstrap = bootstrap_template(data_masses[0], mc_masses[0], edges)
    fit["uncertainty_status"] = "conditional bootstrap available; physics systematics unresolved"
    closure = heldout_closure(
        data_masses[1], mc_masses[1], edges, fit["parameters"], bootstrap["parameters"]
    )
    baseline = heldout_closure(data_masses[1], mc_masses[1], edges, [1, 0.0005, 0])
    report = {
        "schema": "heplab-cms-mass-template-v1",
        "data_record": 30522,
        "mc_record": 35671,
        "data_selected_pairs_sha256": measured_report["selected_pairs_sha256"],
        "mc_source": source,
        "mc_selected_pairs": list(map(len, mc_masses)),
        "data_selected_pairs": list(map(len, data_masses)),
        "fit_window_gev": [75, 105],
        "edges_gev": edges.tolist(),
        "fit": fit,
        "bootstrap": bootstrap,
        "heldout": closure,
        "baseline_heldout": baseline,
        "selection": measured_report["selection"],
        "status": "exploratory_mass_template_closure_passed"
        if closure["passed"]
        else "closure_failed",
        "detector_calibration_status": "not_validated",
        "production_transport_parameters_changed": False,
        "limitations": [
            "One file/range per population, not run-independent final validation",
            "No official Rochester/efficiency corrections or pileup reweighting applied",
            "Uniform nuisance background is not an independently validated background model",
            "Physics-systematic uncertainty is not included in closure",
            "Mass scale/sigma are aggregate spectrum parameters, not per-muon corrections",
            "No field, material or laboratory chamber calibration follows from this fit",
        ],
    }
    for output in [
        folder / "mass-calibration.json",
        ROOT / "src/heplab/data/reference/cms-mass-calibration.json",
    ]:
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (ROOT / "src/heplab/data/reference/cms-z-template-candidates.json").write_text(
        json.dumps(z_input_fixture, separators=(",", ":")) + "\n", encoding="utf8"
    )
    print(
        json.dumps(
            {
                "mc_pairs": report["mc_selected_pairs"],
                "fit": fit,
                "heldout_pvalue": closure["pvalue"],
                "status": report["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
