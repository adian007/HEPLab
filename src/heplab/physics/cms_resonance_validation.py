"""Fit frozen CMS resonance candidates and evaluate guarded reference checks."""

from __future__ import annotations

import math
from collections.abc import Iterable
from hashlib import sha256

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, ndtr

RESONANCES = {
    "jpsi": {"mass_gev": 3.096900, "window_gev": [2.75, 3.35]},
    "upsilon_1s": {"mass_gev": 9.460300, "window_gev": [8.85, 9.72]},
    "upsilon_2s": {"mass_gev": 10.023260, "window_gev": [9.72, 10.25]},
    "upsilon_3s": {"mass_gev": 10.3552, "window_gev": [10.25, 10.85]},
}

EVENT_SPLIT_ALGORITHM = "sha256-run-lumi-event-mod5-v1"
HELDOUT_MODULUS = 5


def select_candidate_index(transverse_momenta: Iterable[tuple[float, float]]) -> int | None:
    """Choose the pair with the largest scalar pT sum, independent of its mass.

    Pair order is the deterministic tie breaker. The function deliberately
    accepts no mass, resonance label, or reference value.
    """
    candidates = tuple(tuple(pair) for pair in transverse_momenta)
    if not candidates:
        return None
    if any(
        len(pair) != 2 or any(not math.isfinite(value) or value < 0 for value in pair)
        for pair in candidates
    ):
        raise ValueError("candidate pT values must be finite and nonnegative")
    return max(range(len(candidates)), key=lambda index: (sum(candidates[index]), -index))


def event_split(run: int, luminosity_block: int, event: int) -> str:
    """Return a stable event-level holdout label from identifiers alone."""
    values = (run, luminosity_block, event)
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("event identity fields must be nonnegative integers")
    key = f"{run}:{luminosity_block}:{event}".encode("ascii")
    bucket = int.from_bytes(sha256(key).digest()[:8], "big") % HELDOUT_MODULUS
    return "heldout" if bucket == 0 else "training"


def _normal_pdf(values: np.ndarray, mean: float, sigma: float) -> np.ndarray:
    z = (values - mean) / sigma
    return np.exp(-0.5 * z * z) / (sigma * math.sqrt(2 * math.pi))


def fit_peak(values: Iterable[float], window: tuple[float, float]) -> dict:
    """Unbinned Gaussian plus exponential-background fit in a fixed window."""
    data = np.asarray(tuple(values), dtype=float)
    low, high = window
    data = data[np.isfinite(data) & (data >= low) & (data <= high)]
    if len(data) < 40:
        return {"entries": int(len(data)), "status": "insufficient_entries"}

    span = high - low
    center = float(np.median(data))
    sigma0 = float(np.clip(np.std(data) / 3, span / 100, span / 8))

    def nll(parameters: np.ndarray) -> float:
        mean, log_sigma, signal_logit, slope = parameters
        sigma = math.exp(float(log_sigma))
        fraction = float(expit(signal_logit))
        norm = ndtr((high - mean) / sigma) - ndtr((low - mean) / sigma)
        if norm <= 1e-14:
            return 1e100
        signal = _normal_pdf(data, mean, sigma) / norm
        exponent = slope * (data - (low + high) / 2)
        if abs(slope) < 1e-7:
            background = np.full_like(data, 1.0 / span)
        else:
            background = np.exp(exponent) * slope / (2 * math.sinh(slope * span / 2))
        density = fraction * signal + (1 - fraction) * background
        if np.any(density <= 0) or not np.all(np.isfinite(density)):
            return 1e100
        return float(-np.log(density).sum())

    result = minimize(
        nll,
        [center, math.log(sigma0), 2.0, 0.0],
        method="L-BFGS-B",
        bounds=[
            (low + span * 0.15, high - span * 0.15),
            (math.log(span / 1000), math.log(span / 2)),
            (-8, 8),
            (-15 / span, 15 / span),
        ],
    )
    if not result.success or not np.isfinite(result.fun):
        return {"entries": int(len(data)), "status": "fit_failed", "message": str(result.message)}
    mean, log_sigma, signal_logit, slope = map(float, result.x)
    signal_count = len(data) * float(expit(signal_logit))
    sigma_uncertainty = math.exp(log_sigma) / math.sqrt(max(1.0, 2 * signal_count))
    mean_uncertainty = math.exp(log_sigma) / math.sqrt(max(1.0, signal_count))
    return {
        "entries": int(len(data)),
        "status": "fit_ok",
        "mean_gev": mean,
        "mean_uncertainty_gev_approx": mean_uncertainty,
        "sigma_gev": math.exp(log_sigma),
        "sigma_uncertainty_gev_approx": sigma_uncertainty,
        "uncertainty_method": (
            "Gaussian Fisher approximation using fitted signal count; "
            "background uncertainty omitted"
        ),
        "signal_fraction": float(expit(signal_logit)),
        "background_slope_per_gev": slope,
        "fit_window_gev": [low, high],
    }


def evaluate_reference(fit: dict, reference: dict) -> dict:
    if fit.get("status") != "fit_ok":
        return {"passed": False, "reason": fit.get("status", "missing_fit")}
    target_mass = reference.get("mass_gev", reference.get("mass"))
    mass_residual = fit["mean_gev"] - target_mass
    mass_tolerance = reference.get("mass_tolerance_gev", reference.get("tolerance"))
    result = {
        "mass_residual_gev": mass_residual,
        "mass_tolerance_gev": mass_tolerance,
        "mass_passed": abs(mass_residual) <= mass_tolerance,
        "passed": abs(mass_residual) <= mass_tolerance,
    }
    if "sigma_tolerance_gev" in reference:
        low, high = reference["sigma_tolerance_gev"]
        result["sigma_tolerance_gev"] = [low, high]
        result["sigma_passed"] = low <= fit["sigma_gev"] <= high
        result["passed"] = result["passed"] and result["sigma_passed"]
    return result
