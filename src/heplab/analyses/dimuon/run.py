"""Validated weighted dimuon processing with explicit event/candidate accounting."""

from __future__ import annotations

import math
from bisect import bisect_right
from itertools import combinations

from ...io.provenance import config_hash
from ...physics import FourVector, WeightedHistogram


def invariant_mass(first: dict, second: dict) -> float:
    vectors = [
        FourVector.from_pt_eta_phi_mass(*(float(obj[k]) for k in ("pt", "eta", "phi", "mass")))
        for obj in (first, second)
    ]
    return (vectors[0] + vectors[1]).physical_mass


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def event_weight(info: dict) -> float:
    value = info.get("weight", 1.0)
    if isinstance(value, dict):
        factors = [value[k] for k in ("generator", "normalization", "pileup")]
        factors.extend(value.get("corrections", {}).values())
        value = math.prod(_finite_number(x, "weight factor") for x in factors)
    weight = _finite_number(value, "event weight")
    if info.get("is_data", info.get("kind") == "data") and weight != 1:
        raise ValueError("collision data cannot carry an undeclared MC weight")
    return weight


def _settings(config):
    allowed = {
        "schema",
        "datasets",
        "selection",
        "binning",
        "fit",
        "systematics",
        "validation",
        "trigger",
        "candidate_policy",
        "limits",
    }
    if set(config) - allowed:
        raise ValueError(f"unknown analysis keys: {sorted(set(config) - allowed)}")
    if config.get("systematics"):
        raise ValueError("systematic variations require a supported variation model")
    selection = config.get("selection", {})
    muon = selection.get("muons", {})
    pairs = selection.get("pairs", {})
    for mapping, allowed_fields in [
        (selection, {"muons", "pairs"}),
        (muon, {"min_pt", "max_abs_eta", "max_rel_iso", "min_n"}),
        (pairs, {"require_opposite_charge", "mass_window", "reference_mass"}),
        (config.get("binning", {}), {"dimuon_mass"}),
        (config.get("trigger", {}), {"paths"}),
        (config.get("validation", {}), {"mode"}),
        (config.get("limits", {}), {"max_candidates"}),
    ]:
        if not isinstance(mapping, dict) or set(mapping) - allowed_fields:
            raise ValueError("unknown or invalid nested analysis configuration")
    pt, eta, iso = (
        _finite_number(muon.get(k, d), k)
        for k, d in (("min_pt", 0), ("max_abs_eta", 2.4), ("max_rel_iso", 0.15))
    )
    minimum = muon.get("min_n", 2)
    if pt < 0 or eta <= 0 or iso < 0 or type(minimum) is not int or minimum < 2:
        raise ValueError("invalid muon thresholds or multiplicity")
    window = pairs.get("mass_window", [0.5, 200.0])
    if len(window) != 2 or not 0 <= _finite_number(window[0], "mass low") < _finite_number(
        window[1], "mass high"
    ):
        raise ValueError("mass window must be increasing and nonnegative")
    opposite = pairs.get("require_opposite_charge", True)
    if type(opposite) is not bool:
        raise ValueError("charge policy must be boolean")
    spec = config.get("binning", {}).get("dimuon_mass", {})
    if set(spec) - {"range", "bins", "log_bins"} or type(spec.get("log_bins", False)) is not bool:
        raise ValueError("unknown or invalid binning configuration")
    bins = spec.get("bins", 400)
    low, high = spec.get("range", [0.5, 200.0])
    low, high = _finite_number(low, "histogram low"), _finite_number(high, "histogram high")
    if type(bins) is not int or not 0 < bins <= 100000 or not low < high:
        raise ValueError("invalid histogram binning")
    if spec.get("log_bins", False):
        if low <= 0:
            raise ValueError("logarithmic bin edges require positive limits")
        edges = tuple(
            math.exp(math.log(low) + i * math.log(high / low) / bins) for i in range(bins + 1)
        )
        edges = (low, *edges[1:-1], high)
    else:
        edges = tuple(low + (high - low) * i / bins for i in range(bins + 1))
    policy = config.get("candidate_policy", "all_pairs")
    if policy not in {"all_pairs", "highest_sum_pt", "closest_to_reference_mass"}:
        raise ValueError("unsupported candidate policy")
    if (
        policy == "closest_to_reference_mass"
        and _finite_number(pairs.get("reference_mass"), "reference mass") <= 0
    ):
        raise ValueError("candidate reference mass must be explicit and positive")
    mode = config.get("validation", {}).get("mode", "exploratory")
    if mode not in {"exploratory", "educational", "measurement"}:
        raise ValueError("unknown validation mode")
    if mode == "measurement" and not config.get("trigger", {}).get("paths"):
        raise ValueError("measurement requires an explicit trigger policy")
    return pt, eta, iso, minimum, window, opposite, edges, policy, mode


def process(events, config: dict) -> dict:
    pt, eta, iso, minimum, window, opposite, edges, policy, mode = _settings(config)
    hist = WeightedHistogram(edges)
    stages = (
        "all",
        "certified",
        "trigger",
        "at_least_two_muons",
        "selected_muons",
        "opposite_charge_pair",
        "mass_window",
    )
    cutflow = dict.fromkeys(stages, 0)
    weighted = {stage: {"sumw": 0.0, "sumw2": 0.0} for stage in stages}
    masses: list[float] = []
    weights: list[float] = []
    event_bin_variance = [0.0] * (len(edges) + 1)
    invalid = 0
    multi_candidate_events = 0
    candidate_limit = config.get("limits", {}).get("max_candidates", 100_000)
    if type(candidate_limit) is not int or candidate_limit <= 0:
        raise ValueError("candidate storage budget must be positive")
    kinds = set()
    definition_ids = set()
    paths = config.get("trigger", {}).get("paths", [])
    if not isinstance(paths, list) or not all(isinstance(x, str) for x in paths):
        raise ValueError("trigger paths must be strings")
    seen: dict[str, int] = {}
    for event in events:
        info = event["EventInfo"]
        if "is_data" in info and type(info["is_data"]) is not bool:
            raise ValueError("event data/simulation flag must be boolean")
        if (
            mode == "measurement"
            and "is_data" not in info
            and info.get("kind") not in {"data", "simulation"}
        ):
            raise ValueError("measurement requires explicit data/simulation kind")
        definition_ids.add(event.get("Definitions", {}).get("muon_iso") or "unknown")
        weight = event_weight(info)
        kind = "data" if info.get("is_data", info.get("kind") == "data") else "simulation"
        kinds.add(kind)
        if "source_id" in info and "source_entry" in info:
            source_id = info["source_id"]
            source_entry = info["source_entry"]
            if source_entry <= seen.get(source_id, -1):
                raise ValueError("duplicate or out-of-order source event")
            if source_id not in seen and len(seen) >= 10000:
                raise ValueError("source identity budget exceeded")
            seen[source_id] = source_entry

        def passed(stage, current_weight=weight):
            cutflow[stage] += 1
            weighted[stage]["sumw"] += current_weight
            weighted[stage]["sumw2"] += current_weight * current_weight

        passed("all")
        if kind == "data" and mode == "measurement" and not info.get("certification_sha256"):
            raise ValueError("measurement data requires certified-run provenance")
        if info.get("certified") is False:
            continue
        if mode == "measurement" and kind == "data" and info.get("certified") is not True:
            raise ValueError("uncertified collision event in measurement")
        passed("certified")
        if paths:
            trigger = event.get("Trigger", {})
            decisions = dict(zip(trigger.get("names", []), trigger.get("fired", []), strict=True))
            if set(paths) - decisions.keys():
                raise ValueError("unknown required trigger decision")
            if not any(decisions[name] is True for name in paths):
                continue
            if mode == "measurement" and trigger.get("source") not in {
                "recorded",
                "validated_emulation",
            }:
                raise ValueError("measurement trigger provenance is missing")
        passed("trigger")
        muons = event.get("Muon") or []
        if len(muons) < minimum:
            continue
        passed("at_least_two_muons")
        selected = []
        for obj in muons:
            isolation = obj.get("iso", obj.get("isolation", {}).get("value"))
            values = [obj.get(k) for k in ("pt", "eta", "phi", "mass")] + [isolation]
            if any(
                v is None
                or isinstance(v, bool)
                or not isinstance(v, int | float)
                or not math.isfinite(v)
                for v in values
            ):
                invalid += 1
                continue
            if obj["pt"] < 0 or obj["mass"] < 0 or isolation < 0:
                invalid += 1
                continue
            if obj["pt"] >= pt and abs(obj["eta"]) <= eta and isolation <= iso:
                if mode == "measurement" and obj.get("quality_flags") is not True:
                    continue
                selected.append(obj)
        if len(selected) < minimum:
            continue
        passed("selected_muons")
        candidates = []
        for a, b in combinations(selected, 2):
            if opposite and (a.get("charge") not in (-1, 1) or b.get("charge") != -a["charge"]):
                continue
            candidates.append((invariant_mass(a, b), a["pt"] + b["pt"]))
        if not candidates:
            continue
        passed("opposite_charge_pair")
        candidates = [(mass, sumpt) for mass, sumpt in candidates if window[0] <= mass < window[1]]
        if not candidates:
            continue
        if policy == "highest_sum_pt":
            candidates = [min(candidates, key=lambda x: (-x[1], x[0]))]
        elif policy == "closest_to_reference_mass":
            reference_mass = config["selection"]["pairs"]["reference_mass"]
            candidates = [min(candidates, key=lambda x: (abs(x[0] - reference_mass), x[0], -x[1]))]
        passed("mass_window")
        if len(candidates) > 1:
            multi_candidate_events += 1
        if len(masses) + len(candidates) > candidate_limit:
            raise ValueError("candidate output budget exceeded")
        event_bins: dict[int, float] = {}
        for mass, _ in candidates:
            hist.fill(mass, weight)
            masses.append(mass)
            weights.append(weight)
            index = bisect_right(edges, mass)
            event_bins[index] = event_bins.get(index, 0) + weight
        for index, contribution in event_bins.items():
            event_bin_variance[index] += contribution * contribution
    snapshot = hist.snapshot()
    return {
        "analysis": "dimuon",
        "analysis_config_sha256": config_hash(config),
        "validation": {
            "mode": mode,
            "state": "unvalidated",
            "limitations": ["calibration and held-out physics acceptance required"],
        },
        "data_kind": next(iter(kinds)) if len(kinds) == 1 else ("mixed" if kinds else "none"),
        "semantics": {"muon_iso": sorted(definition_ids), "units": "GeV"},
        "events_processed": cutflow["all"],
        "cutflow": cutflow,
        "cutflow_weighted": weighted,
        "invalid_objects": invalid,
        "multi_candidate_events": multi_candidate_events,
        "candidate_policy": policy,
        "histogram": {
            "observable": "dimuon_mass",
            "units": "GeV",
            "bins": len(edges) - 1,
            "range": [edges[0], edges[-1]],
            "edges": list(edges),
            "counts": snapshot["sumw_with_flow"][1:-1],
            "sumw2": snapshot["sumw2_with_flow"][1:-1],
            "event_sumw2": event_bin_variance[1:-1],
            "entries": len(masses),
            "flow": snapshot,
        },
        "masses": masses,
        "candidate_weights": weights,
    }
