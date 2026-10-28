"""Compatible shape comparison with finite normalization and ratio uncertainty.

This is a statistical comparison, not truth-based efficiency calibration.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


def compare(data_path: str | Path, sim_path: str | Path) -> dict:
    import numpy as np

    data = json.loads(Path(data_path).read_text(encoding="utf8"))
    sim = json.loads(Path(sim_path).read_text(encoding="utf8"))
    left, right = data["histogram"], sim["histogram"]
    for key in ("observable", "units", "edges"):
        if key not in left or left[key] != right.get(key):
            raise ValueError(f"incompatible or missing comparison {key}")
    for key in ("analysis_config_sha256", "candidate_policy", "semantics"):
        if key not in data or data[key] != sim.get(key):
            raise ValueError(f"incompatible or missing comparison {key}")
    if data.get("data_kind") != "data" or sim.get("data_kind") != "simulation":
        raise ValueError("comparison requires declared data and simulation artifacts")
    if data["semantics"].get("muon_iso") == ["unknown"]:
        raise ValueError("comparison requires known isolation definitions")
    # Multi-pair event covariance needs a full cross-bin event ledger, not only its diagonal.
    if data.get("multi_candidate_events", 0) or sim.get("multi_candidate_events", 0):
        raise ValueError("comparison of clustered candidates requires cross-bin event covariance")

    def shape(histogram):
        y = np.asarray(histogram["counts"], dtype=float)
        variance = np.asarray(histogram["sumw2"], dtype=float)
        if (
            len(y) != len(variance)
            or len(y) != len(histogram["edges"]) - 1
            or not np.isfinite(y).all()
            or not np.isfinite(variance).all()
            or np.any(variance < 0)
            or np.any(y < 0)
            or y.sum() <= 0
        ):
            raise ValueError("invalid/nonpositive normalized comparison population")
        total = y.sum()
        jacobian = (np.eye(len(y)) - np.outer(y / total, np.ones(len(y)))) / total
        covariance = (jacobian * variance) @ jacobian.T
        return y / total, covariance

    d, dcov = shape(left)
    s, scov = shape(right)
    ratio: list[float | None] = []
    ratio_variance: list[float | None] = []
    for i, (a, b) in enumerate(zip(d, s, strict=True)):
        if a == 0:
            ratio.append(None)
            ratio_variance.append(None)
        else:
            ratio.append(float(b / a))
            variance = float(scov[i, i] / a**2 + b**2 * dcov[i, i] / a**4)
            if not math.isfinite(variance):
                raise ValueError("comparison variance overflow")
            ratio_variance.append(max(0.0, variance))
    return {
        "comparison": "normalized_shape",
        "validation": "unvalidated",
        "data_artifact": str(data_path),
        "simulation_artifact": str(sim_path),
        "normalized_bin_ratio_sim_over_data": ratio,
        "ratio_variance": ratio_variance,
        "data_normalized_covariance": dcov.tolist(),
        "simulation_normalized_covariance": scov.tolist(),
        "undefined_ratio_reason": "zero data denominator",
        "assumption": "statistically independent data and MC; systematic covariance not included",
        "caveat": "Shape agreement alone does not establish detector efficiency or calibration.",
    }
