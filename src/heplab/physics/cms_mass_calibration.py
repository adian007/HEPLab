"""Conditional measured dimuon mass-template fitting, not detector calibration.

The nuisance parameters describe one selected mass spectrum. They cannot be
applied as per-muon momentum corrections or as field/material calibrations.
"""

from __future__ import annotations

import math
from itertools import combinations

from ..analyses.dimuon.run import invariant_mass


def selected_pair(event):
    """Same tight/isolated OS highest-sum-pT pair for measured data and MC."""
    muons = []
    for index, pt in enumerate(event["Muon_pt"]):
        if (
            float(pt) > 15
            and abs(float(event["Muon_eta"][index])) < 2.4
            and bool(event["Muon_tightId"][index])
            and float(event["Muon_pfRelIso04_all"][index]) < 0.15
        ):
            muon = {
                key: float(event["Muon_" + key][index])
                for key in ("pt", "eta", "phi", "mass", "charge")
            }
            if not all(math.isfinite(v) for v in muon.values()) or muon["charge"] not in (-1, 1):
                raise ValueError("invalid selected CMS muon")
            muons.append(muon)
    pairs = [
        (a, b)
        for a, b in combinations(muons, 2)
        if a["charge"] * b["charge"] < 0 and max(a["pt"], b["pt"]) > 25
    ]
    if not pairs:
        return None
    a, b = max(pairs, key=lambda pair: pair[0]["pt"] + pair[1]["pt"])
    return {"mass_gev": invariant_mass(a, b), "muons": [a, b]}


def kernel(masses, edges, parameters):
    """Integrated Gaussian broadening of a frozen MC mass population."""
    import numpy as np
    from scipy.special import ndtr

    values, edges = np.asarray(masses, dtype=float), np.asarray(edges, dtype=float)
    scale, sigma, background = parameters
    if (
        values.ndim != 1
        or len(values) < 100
        or not np.isfinite(values).all()
        or np.min(values) <= 0
        or edges.ndim != 1
        or not np.isfinite(edges).all()
        or len(edges) < 3
        or not (np.diff(edges) > 0).all()
        or not 0.98 <= scale <= 1.02
        or not 0.0005 <= sigma <= 0.05
        or not 0 <= background <= 0.15
    ):
        raise ValueError("invalid mass-template domain")
    cumulative = ndtr((edges[:, None] - scale * values) / (sigma * values))
    matrix = np.diff(cumulative, axis=0)
    total = matrix.sum()
    if total <= 0:
        raise ValueError("empty MC template in fit window")
    signal = matrix.sum(axis=1) / total
    uniform = np.diff(edges) / (edges[-1] - edges[0])
    return (1 - background) * signal + background * uniform, matrix, signal


def fit_template(data_masses, mc_masses, edges):
    import numpy as np
    from scipy.optimize import minimize

    counts = np.histogram(data_masses, edges)[0]
    if counts.sum() < 1000:
        raise ValueError("mass-template fit requires at least 1000 selected data pairs")

    def objective(value):
        parameters = [1 + value[0] / 100, value[1] / 100, value[2] / 100]
        probabilities, _, _ = kernel(mc_masses, edges, parameters)
        return -float(counts @ np.log(np.maximum(probabilities, 1e-300))) / counts.sum()

    solutions = [
        minimize(
            objective,
            [0, width, 2],
            method="L-BFGS-B",
            bounds=[(-2, 2), (0.05, 5), (0, 15)],
            options={"ftol": 1e-12, "maxiter": 200},
        )
        for width in (0.5, 2.0)
    ]
    valid = [solution for solution in solutions if solution.success and math.isfinite(solution.fun)]
    if not valid:
        raise ValueError("mass-template optimization did not converge")
    solution = min(valid, key=lambda item: item.fun)
    parameters = [
        1 + float(solution.x[0]) / 100,
        float(solution.x[1]) / 100,
        float(solution.x[2]) / 100,
    ]
    return {
        "mass_scale": parameters[0],
        "additional_fractional_mass_sigma": parameters[1],
        "uniform_background_fraction": parameters[2],
        "mean_negative_log_likelihood": float(solution.fun),
        "optimizer_success": True,
        "parameters": parameters,
        "uncertainty_status": "training-parameter and physics-systematic uncertainties unresolved",
        "scope": "selected 1D mass spectrum only; not per-muon response or detector calibration",
    }


def bootstrap_template(data_masses, mc_masses, edges, replicates=100, seed=20261027):
    """Event-pair bootstrap of both training populations, with frozen seed/count."""
    import numpy as np

    if type(replicates) is not int or not 20 <= replicates <= 500:
        raise ValueError("bootstrap replicate budget must be in [20,500]")
    rng = np.random.default_rng(seed)
    data, mc = np.asarray(data_masses), np.asarray(mc_masses)
    samples = []
    for _ in range(replicates):
        try:
            fitted = fit_template(rng.choice(data, len(data)), rng.choice(mc, len(mc)), edges)
        except ValueError:
            continue
        samples.append(fitted["parameters"])
    if len(samples) < 0.9 * replicates:
        raise ValueError("too many bootstrap fits failed")
    return {
        "seed": seed,
        "requested": replicates,
        "successful": len(samples),
        "parameters": samples,
        "intervals_95_percent": np.quantile(samples, [0.025, 0.975], axis=0).T.tolist(),
        "scope": "conditional model statistical uncertainty; physics systematics excluded",
    }


def heldout_closure(data_masses, mc_masses, edges, parameters, parameter_samples=None):
    """Multinomial residuals with normalized finite-MC template covariance.

    Central fit parameters stay frozen. Optional training bootstrap propagates
    conditional fit uncertainty; physics systematics remain excluded.
    """
    import numpy as np
    from scipy.stats import chi2

    observed = np.histogram(data_masses, edges)[0]
    total = observed.sum()
    if total < 1000:
        raise ValueError("held-out closure requires 1000 selected pairs")
    probabilities, matrix, signal = kernel(mc_masses, edges, parameters)
    expected = total * probabilities
    column_sums = matrix.sum(axis=0)
    jacobian = (matrix - signal[:, None] * column_sums) / matrix.sum()
    covariance_mc = (1 - parameters[2]) ** 2 * (jacobian @ jacobian.T)
    covariance_data = total * (np.diag(probabilities) - np.outer(probabilities, probabilities))
    covariance = covariance_data + total**2 * covariance_mc
    includes = ["conditional data counts", "finite held-out MC template"]
    if parameter_samples is not None:
        if len(parameter_samples) < 20:
            raise ValueError("too few frozen parameter bootstrap samples")
        predictions = np.array(
            [kernel(mc_masses, edges, values)[0] for values in parameter_samples]
        )
        covariance += total**2 * np.cov(predictions, rowvar=False)
        includes.append("training data and MC bootstrap fit uncertainty")
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    supported = eigenvalues > max(eigenvalues.max() * 1e-10, 1e-12)
    residual = observed - expected
    projected = eigenvectors[:, supported].T @ residual
    statistic = float(np.sum(projected**2 / eigenvalues[supported]))
    degrees = int(supported.sum())
    pvalue = float(chi2.sf(statistic, degrees))
    return {
        "statistic": statistic,
        "degrees_of_freedom": degrees,
        "pvalue": pvalue,
        "minimum_pvalue": 0.01,
        "minimum_expected_per_bin": float(expected.min()),
        "passed": bool(pvalue >= 0.01 and expected.min() >= 5),
        "observed": observed.tolist(),
        "expected": expected.tolist(),
        "covariance_includes": includes,
        "covariance_omits": (["training fit parameters"] if parameter_samples is None else [])
        + ["physics systematics"],
    }
