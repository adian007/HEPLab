"""Selected reconstructed dimuons from generated DELPHES events.

One pair per event is ranked by scalar pT sum before the mass-window cut.
Signed event weights, squared weights, and flow bins remain explicit.
"""

from __future__ import annotations

import math
import threading
from bisect import bisect_right
from collections import Counter
from itertools import combinations

from ..physics.reference import FourVector, WeightedHistogram


def analyze(events, config, cancel: threading.Event | None = None, progress=None) -> dict:
    labels = [
        "Generated events",
        "Two kinematic muons",
        "Opposite-charge pair",
        "Isolated pair",
        "Mass window",
    ]
    weights: list[list[float]] = [[] for _ in labels]
    rows, samples, pairs = [], [], []
    low, high = config.mass_min_gev, config.mass_max_gev
    histograms = {
        "mass": WeightedHistogram(tuple(low + (high - low) * i / 24 for i in range(25))),
        "pt": WeightedHistogram(tuple(5.0 * i for i in range(41))),
        "eta": WeightedHistogram(tuple(-3.0 + i * 0.25 for i in range(25))),
        "met": WeightedHistogram(tuple(5.0 * i for i in range(41))),
    }
    clustered: dict[str, list[list[float]]] = {
        key: [[] for _ in range(len(histograms[key].edges) + 1)] for key in ("pt", "eta")
    }
    for index, event in enumerate(events):
        if cancel is not None and cancel.is_set():
            raise RuntimeError("collision analysis cancelled")
        weight = float(event["EventInfo"]["weight"])
        if not math.isfinite(weight):
            raise ValueError("nonfinite event weight")
        weights[0].append(weight)
        if event["Muon"] is None:
            raise ValueError("DELPHES output lacks the reconstructed Muon collection")
        muons = event["Muon"]
        if len(muons) > 128:
            raise ValueError("reconstructed-muon budget exceeded")

        def valid(muon):
            return (
                all(
                    isinstance(muon.get(k), float | int) and math.isfinite(muon[k])
                    for k in ("pt", "eta", "phi", "mass", "charge")
                )
                and muon["pt"] > 0
            )

        if not all(valid(m) for m in muons):
            raise ValueError("invalid reconstructed muon kinematics")
        selected = [
            m
            for m in muons
            if m["pt"] >= config.muon_pt_min_gev and abs(m["eta"]) < config.muon_abs_eta_max
        ]
        for m in muons:
            samples.append(
                {
                    "event": index,
                    "object_id": m["object_id"],
                    "pt_gev": m["pt"],
                    "eta": m["eta"],
                    "iso": m["iso"],
                    "weight": weight,
                }
            )
            histograms["pt"].fill(m["pt"], weight)
            histograms["eta"].fill(m["eta"], weight)
        # Muons from one event are correlated. Store per-event bin variances in
        # addition to the per-object sumw2 so plotted uncertainties retain this.
        for key, field in [("pt", "pt"), ("eta", "eta")]:
            counts = Counter(bisect_right(histograms[key].edges, m[field]) for m in muons)
            for bucket, count in counts.items():
                clustered[key][bucket].append((weight * count) ** 2)
        met = event["MET"]["pt"]
        if met is not None:
            histograms["met"].fill(met, weight)
        row = {
            "event": index,
            "weight": weight,
            "muons": len(muons),
            "jets": len(event["Jet"] or []),
            "met_gev": met,
            "selected": False,
            "mass_gev": None,
            "pair_ids": [],
        }
        rows.append(row)
        if progress:
            progress(index + 1)
        if len(selected) < 2:
            continue
        weights[1].append(weight)
        candidates = [(a, b) for a, b in combinations(selected, 2) if a["charge"] * b["charge"] < 0]
        if not candidates:
            continue
        weights[2].append(weight)
        candidates = [
            (a, b)
            for a, b in candidates
            if all(
                isinstance(m.get("iso"), float | int)
                and math.isfinite(m["iso"])
                and 0 <= m["iso"] <= config.muon_iso_max
                for m in (a, b)
            )
        ]
        if not candidates:
            continue
        weights[3].append(weight)
        first, second = min(
            candidates,
            key=lambda p: (-(p[0]["pt"] + p[1]["pt"]), p[0]["object_id"], p[1]["object_id"]),
        )

        def vector(muon):
            return FourVector.from_pt_eta_phi_mass(
                muon["pt"], muon["eta"], muon["phi"], muon["mass"]
            )

        mass = (vector(first) + vector(second)).physical_mass
        row.update(mass_gev=mass, pair_ids=[first["object_id"], second["object_id"]])
        # Histogram all selected OS isolated pairs before the mass-window cut.
        # Its flow bins retain candidates outside the requested window.
        histograms["mass"].fill(mass, weight)
        if not low <= mass < high:
            continue
        weights[4].append(weight)
        row["selected"] = True
        pairs.append(
            {"event": index, "mass_gev": mass, "weight": weight, "pair_ids": row["pair_ids"]}
        )
    snapshots = {key: value.snapshot() for key, value in histograms.items()}
    for key, buckets in clustered.items():
        snapshots[key]["event_sumw2_with_flow"] = [math.fsum(v) for v in buckets]
    return {
        "kind": "collision",
        "events": len(rows),
        "particles": len(samples),
        "scope": (
            "PYTHIA8 pp → gamma*/Z → muons; DELPHES CMS reconstructed objects; "
            "no additional smearing"
        ),
        "selection": {
            "muon_pt_min_gev": config.muon_pt_min_gev,
            "muon_abs_eta_max": config.muon_abs_eta_max,
            "muon_iso_max": config.muon_iso_max,
            "mass_min_gev": low,
            "mass_max_gev": high,
            "pair_policy": "highest_scalar_pt_before_mass_cut",
            "isolation_definition": "DELPHES card IsolationVar, not measured CMS identification",
        },
        "cutflow": [
            {
                "stage": name,
                "events": len(w),
                "sumw": math.fsum(w),
                "sumw2": math.fsum(x * x for x in w),
            }
            for name, w in zip(labels, weights, strict=True)
        ],
        "histograms": snapshots,
        "histogram_scope": {
            "mass": "one highest-scalar-pT OS isolated pair per event, before mass window",
            "pt": "all reconstructed muons, before cuts",
            "eta": "all reconstructed muons, before cuts",
            "met": "all events",
        },
        "samples": samples,
        "pairs": pairs,
        "event_rows": rows,
        "selected_events": len(pairs),
        "normalization": (
            "raw signed generator weights; error bars sqrt(event-level sumw2); "
            "no luminosity scaling"
        ),
    }
