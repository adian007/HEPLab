"""Reference calibration with frozen splits and explicit, bounded acceptance gates."""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..io.provenance import config_hash, file_hash

REFERENCE = Path(__file__).parents[1] / "data/reference"


def interpolate(knots, energy):
    if not math.isfinite(energy) or not knots[0][0] <= energy <= knots[-1][0]:
        raise ValueError("outside calibrated stopping-power domain")
    for a, b in zip(knots, knots[1:], strict=False):
        if a[0] <= energy <= b[0]:
            t = math.log(energy / a[0]) / math.log(b[0] / a[0])
            return a[1] + t * (b[1] - a[1])
    raise ValueError("invalid interpolation knots")


def calibrate_silicon():
    source = json.loads((REFERENCE / "silicon-muon.json").read_text())
    raw = REFERENCE / "muE_silicon_Si.txt"
    if file_hash(raw) != source["source_sha256"]:
        raise ValueError("PDG reference checksum mismatch")
    rows = source["rows"]
    training = [i for i in range(len(rows)) if i % 2 == 0 or i == len(rows) - 1]
    heldout = [i for i in range(len(rows)) if i not in training]
    knots = [[rows[i]["kinetic_gev"], rows[i]["ionization_gev_per_m"]] for i in training]
    errors = [
        {
            "row": i,
            "energy_gev": rows[i]["kinetic_gev"],
            "relative_error": interpolate(knots, rows[i]["kinetic_gev"])
            / rows[i]["ionization_gev_per_m"]
            - 1,
        }
        for i in heldout
    ]
    maximum = max(abs(row["relative_error"]) for row in errors)
    model = {
        "id": "pdg-si-muon-loglinear-split-v1",
        "scope": "mean ionization, muons in silicon only",
        "source_sha256": source["source_sha256"],
        "source_url": source["source_url"],
        "training_rows": training,
        "heldout_rows": heldout,
        "knots": knots,
        "acceptance": {"max_abs_relative_error": 0.02, "chosen_before_fit": True},
        "heldout_errors": errors,
        "max_abs_relative_error": maximum,
        "status": "reference_calibrated" if maximum <= 0.02 else "failed",
        "not_established": [
            "experimental CMS calibration",
            "radiative or stochastic energy-loss validation",
        ],
    }
    model["sha256"] = config_hash(model)
    return model


def matched_sample(path):
    """Read only needed leaves; stable truth muons, one-to-one charge-aware matching."""
    import uproot

    records = []
    branches = ["Event.Weight", *["Particle." + k for k in ("PID", "Status", "PT", "Eta", "Phi")]]
    branches += ["Muon." + k for k in ("PT", "Eta", "Phi", "Charge")]
    truth_count = 0
    with uproot.open(path) as root:
        for chunk in root["Delphes"].iterate(branches, step_size=128, library="ak"):
            for row in chunk:
                if row["Event.Weight"].to_list() != [1.0]:
                    raise ValueError(
                        "reference response calibration requires unit-weight LO events"
                    )
                truth = []
                for i, (pid, status, pt, eta, phi) in enumerate(
                    zip(
                        *[
                            row["Particle." + k].to_list()
                            for k in ("PID", "Status", "PT", "Eta", "Phi")
                        ],
                        strict=True,
                    )
                ):
                    if abs(pid) == 13 and status == 1 and 5 <= pt <= 200 and abs(eta) < 2.4:
                        truth.append((i, pid, pt, eta, phi))
                reconstructed = list(
                    zip(
                        *[row["Muon." + k].to_list() for k in ("PT", "Eta", "Phi", "Charge")],
                        strict=True,
                    )
                )
                edges = []
                for t, (_, pid, _pt, eta, phi) in enumerate(truth):
                    for r, (_rpt, reta, rphi, charge) in enumerate(reconstructed):
                        dr = math.hypot(eta - reta, math.remainder(phi - rphi, math.tau))
                        if dr < 0.05 and charge == (-1 if pid > 0 else 1):
                            edges.append((dr, t, r))
                used_t, used_r = set(), set()
                matches = {}
                for _, t, r in sorted(edges):
                    if t not in used_t and r not in used_r:
                        matches[t] = r
                        used_t.add(t)
                        used_r.add(r)
                for t, (_, _pid, pt, eta, _phi) in enumerate(truth):
                    matched_index = matches.get(t)
                    records.append(
                        {
                            "pt": pt,
                            "eta": eta,
                            "matched": matched_index is not None,
                            "log_ratio": math.log(reconstructed[matched_index][0] / pt)
                            if matched_index is not None
                            else None,
                        }
                    )
                truth_count += len(truth)
    return records, truth_count


def calibrate_delphes(training_path, validation_path):
    if file_hash(training_path) == file_hash(validation_path):
        raise ValueError("calibration and validation populations must differ")
    manifests = [
        json.loads((Path(path).parent / "run.json").read_text(encoding="utf8"))
        for path in (training_path, validation_path)
    ]
    first, second = manifests
    for path, manifest in zip((training_path, validation_path), manifests, strict=True):
        if file_hash(path) != manifest["files"]["events.root"]:
            raise ValueError("reference ROOT payload differs from committed manifest")
    if first["seed"] == second["seed"]:
        raise ValueError("training and held-out generator seeds must differ")
    for key in ("process", "versions", "beam_energy_total_gev"):
        if first[key] != second[key]:
            raise ValueError("reference populations have incompatible generation conditions")
    if first["runtime"]["cards_sha256"] != second["runtime"]["cards_sha256"]:
        raise ValueError("reference detector cards differ")
    training, _ = matched_sample(training_path)
    validation, _ = matched_sample(validation_path)
    bins = [(0, 0.9), (0.9, 1.7), (1.7, 2.4)]
    output = []
    # Predeclared transfer-model gates; failure is retained, not tuned away.
    gates = {
        "min_training_matches": 100,
        "min_validation_matches": 100,
        "max_abs_log_bias_difference": 0.01,
        "width_ratio_range": [0.6, 1.4],
        "max_efficiency_pull": 3.5,
    }
    for low, high in bins:
        populations = [
            [x for x in population if low <= abs(x["eta"]) < high]
            for population in (training, validation)
        ]
        statistics = []
        for population in populations:
            values = sorted(x["log_ratio"] for x in population if x["matched"])
            if len(values) < 2:
                raise ValueError("insufficient matched response data")
            mean = sum(values) / len(values)
            width = math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))
            statistics.append(
                {
                    "denominator": len(population),
                    "matched": len(values),
                    "efficiency": len(values) / len(population),
                    "log_bias": mean,
                    "log_width": width,
                    "log_bias_standard_error": width / math.sqrt(len(values)),
                    "efficiency_wilson_95": wilson(len(values), len(population)),
                    "fraction_beyond_three_sigma": sum(abs(x - mean) > 3 * width for x in values)
                    / len(values),
                }
            )
        train, valid = statistics
        width_ratio = valid["log_width"] / train["log_width"]
        pooled = (train["matched"] + valid["matched"]) / (
            train["denominator"] + valid["denominator"]
        )
        error = math.sqrt(
            max(
                1e-12, pooled * (1 - pooled) * (1 / train["denominator"] + 1 / valid["denominator"])
            )
        )
        pull = (valid["efficiency"] - train["efficiency"]) / error
        passed = (
            train["matched"] >= 100
            and valid["matched"] >= 100
            and abs(train["log_bias"] - valid["log_bias"]) <= 0.01
            and 0.6 <= width_ratio <= 1.4
            and abs(pull) <= 3.5
        )
        output.append(
            {
                "eta_abs": [low, high],
                "training": train,
                "heldout": valid,
                "width_ratio": width_ratio,
                "efficiency_pull": pull,
                "passed": passed,
            }
        )
    model = {
        "id": "delphes-dy-muon-transfer-v1",
        "reference": "PYTHIA8 8.312 / DELPHES 3.5.1 fixed CMS card",
        "domain": {
            "pt_gev": [5, 200],
            "abs_eta": [0, 2.4],
            "process": "pp gamma*/Z to mumu 60–120 GeV, no pileup",
        },
        "matching": {"max_delta_r": 0.05, "charge_aware": True, "one_to_one": True},
        "training_sha256": file_hash(training_path),
        "heldout_sha256": file_hash(validation_path),
        "split": {
            "training_seed": first["seed"],
            "heldout_seed": second["seed"],
            "training_events": first["summary"]["events"],
            "heldout_events": second["summary"]["events"],
        },
        "gates": gates,
        "bins": output,
        "status": "reference_calibrated" if all(x["passed"] for x in output) else "failed",
        "limits": [
            "eta-binned transfer, pT dependence and non-Gaussian tails unresolved",
            "efficiency includes the declared DY selection and DELPHES object definitions",
            "not an experimental CMS calibration",
        ],
    }
    model["sha256"] = config_hash(model)
    return model


def wilson(successes: int, total: int) -> list[float]:
    if not 0 <= successes <= total or total <= 0:
        raise ValueError("invalid efficiency population")
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def muon_response_parameters(pt: float, eta: float) -> dict:
    payload = json.loads((REFERENCE / "muon-response-calibration.json").read_text())
    if config_hash({k: v for k, v in payload.items() if k != "sha256"}) != payload.get("sha256"):
        raise ValueError("response calibration checksum mismatch")
    if payload["status"] != "reference_calibrated":
        raise ValueError("response reference validation did not pass")
    if not math.isfinite(pt) or not math.isfinite(eta) or not 5 <= pt <= 200 or not abs(eta) < 2.4:
        raise ValueError("outside DY reference-response calibration domain")
    for row in payload["bins"]:
        if row["eta_abs"][0] <= abs(eta) < row["eta_abs"][1]:
            fit = row["training"]
            sigma = fit["log_width"]
            return {
                "efficiency": fit["efficiency"],
                "relative_pt_resolution": math.sqrt(math.expm1(sigma * sigma)),
                "momentum_scale": math.exp(fit["log_bias"] + 0.5 * sigma * sigma),
                "calibration_id": payload["id"],
                "calibration_sha256": payload["sha256"],
                "validation_scope": (
                    "eta-bin aggregates in the DY reference population; "
                    "pT-local response unvalidated"
                ),
            }
    raise ValueError("no calibration bin")
