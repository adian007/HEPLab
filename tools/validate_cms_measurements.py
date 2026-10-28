"""Build a certified measured Z->mumu target with a frozen held-out split.

Empirical shape validation is not a detector-resolution or momentum-scale fit.
No simulator parameter is tuned from the observed Z peak.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import uproot
from scipy.stats import ks_2samp

from heplab.io.certification import LumiMask
from heplab.physics.cms_mass_calibration import selected_pair

ROOT = Path(__file__).resolve().parents[1]


def identity_split(run: int, lumi: int, event: int) -> int:
    key = f"cms-z-reference-v1:{run}:{lumi}:{event}".encode()
    return hashlib.sha256(key).digest()[0] & 1


def main():
    folder = ROOT / "artifacts/cms/measured"
    path = folder / "run2016g-100k.root"
    provenance = json.loads((folder / "source.json").read_text(encoding="utf8"))
    if hashlib.sha256(path.read_bytes()).hexdigest() != provenance["derived_file_sha256"]:
        raise ValueError("derived measured-data sample identity changed")
    mask = LumiMask(
        ROOT / "manifests/certification/Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.json"
    )
    with uproot.open(path) as root:
        events = root["Events"].arrays(provenance["branches"])
    masses: list[list[float]] = [[], []]
    identities, candidates = set(), []
    counts = dict.fromkeys(
        ["input", "certified", "trigger", "two_selected_muons", "mass_window"], 0
    )
    for event in events:
        counts["input"] += 1
        run, lumi, number = (int(event[k]) for k in ("run", "luminosityBlock", "event"))
        identity = (run, lumi, number)
        if identity in identities:
            raise ValueError("duplicate measured event identity")
        identities.add(identity)
        if not mask.accepts(run, lumi):
            continue
        counts["certified"] += 1
        if not (
            bool(event["HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ"])
            or bool(event["HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ"])
        ):
            continue
        counts["trigger"] += 1
        pair = selected_pair(event)
        if pair is None:
            continue
        counts["two_selected_muons"] += 1
        a, b = pair["muons"]
        mass = pair["mass_gev"]
        if not 60 <= mass < 120:
            continue
        counts["mass_window"] += 1
        split = identity_split(run, lumi, number)
        masses[split].append(mass)
        candidates.append(
            {
                "run": run,
                "lumi": lumi,
                "event": number,
                "split": split,
                "mass_gev": mass,
                "muons": [a, b],
            }
        )
    if min(map(len, masses)) < 100:
        raise ValueError("too few selected dimuons to construct a measured reference")
    ks = ks_2samp(*masses, method="asymp")
    summaries = [
        {
            "pairs": len(values),
            "mean_gev": float(np.mean(values)),
            "quantiles_gev": np.quantile(values, [0.16, 0.5, 0.84]).tolist(),
        }
        for values in masses
    ]
    edges = np.linspace(60, 120, 61)
    histograms = [np.histogram(values, edges)[0].tolist() for values in masses]
    adequate = min(map(len, masses)) >= 1000
    report = {
        "schema": "heplab-measured-cms-reference-v1",
        "data_source": provenance,
        "certification_sha256": mask.sha256,
        "cutflow": counts,
        "split": "SHA256(cms-z-reference-v1:run:lumi:event) first byte parity",
        "selection": (
            "certified; either named DZ dimuon trigger; tight muons; "
            "relIso04<0.15; |eta|<2.4; pT>15, leading>25 GeV; "
            "OS highest-sum-pT pair; 60<=mass<120 GeV"
        ),
        "training": summaries[0],
        "heldout": summaries[1],
        "histogram": {
            "edges_gev": edges.tolist(),
            "training": histograms[0],
            "heldout": histograms[1],
        },
        "consistency": {
            "ks_statistic": float(ks.statistic),
            "ks_pvalue": float(ks.pvalue),
            "minimum_pairs_per_split": 1000,
            "minimum_pvalue": 0.01,
            "passed": bool(adequate and ks.pvalue >= 0.01),
        },
        "status": "measured_reference_ready"
        if adequate and ks.pvalue >= 0.01
        else "insufficient_or_inconsistent",
        "detector_calibration_status": (
            "blocked: equivalent selected MC and era-matched correction payload required"
        ),
        "limitations": [
            "First 100k entries of one file; not a luminosity-representative Run2016G sample",
            "Trigger accepted at event level; no trigger-object matching or efficiency measurement",
            "Observed Z width includes natural width, FSR, backgrounds and selection",
            "No Rochester correction applied; no raw-peak-to-PDG scale calibration",
            "Split consistency cannot validate field/material maps or reconstruction response",
        ],
    }
    (folder / "selected-pairs.json").write_text(json.dumps(candidates) + "\n", encoding="utf8")
    report["selected_pairs_sha256"] = hashlib.sha256(
        (folder / "selected-pairs.json").read_bytes()
    ).hexdigest()
    for output in [
        folder / "validation.json",
        ROOT / "src/heplab/data/reference/cms-measured-validation.json",
    ]:
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "cutflow": counts,
                "training": summaries[0],
                "heldout": summaries[1],
                "consistency": report["consistency"],
            }
        )
    )


if __name__ == "__main__":
    main()
