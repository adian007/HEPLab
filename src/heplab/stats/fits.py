"""Finite-window normalized teaching fit with explicit diagnostic/failure state."""

from __future__ import annotations

from enum import Enum, auto


class FitBackend(Enum):
    AUTO = auto()
    CPU = auto()
    GPU = auto()


class BackendNotAvailable(RuntimeError):
    pass


def mixture_density(values, mean: float, sigma: float, signal_fraction: float, limits):
    import numpy as np
    from scipy.stats import truncnorm

    low, high = limits
    if (
        not np.isfinite([mean, sigma, signal_fraction, low, high]).all()
        or sigma <= 0
        or low >= high
        or not 0 <= signal_fraction <= 1
    ):
        raise ValueError("invalid mixture model domain")
    x = np.asarray(values, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError("nonfinite fit observation")
    gaussian = truncnorm.pdf(x, (low - mean) / sigma, (high - mean) / sigma, loc=mean, scale=sigma)
    uniform = np.where((x >= low) & (x <= high), 1 / (high - low), 0)
    return signal_fraction * gaussian + (1 - signal_fraction) * uniform


def unbinned_fit(model_spec: dict, backend: FitBackend = FitBackend.AUTO):
    if backend is FitBackend.GPU:
        raise BackendNotAvailable("GPU fitting has no validated backend")
    if model_spec.get("model", "gaussian_plus_uniform") != "gaussian_plus_uniform":
        raise ValueError("unsupported fit model")
    import numpy as np

    try:
        from iminuit import Minuit
    except ImportError as exc:
        raise BackendNotAvailable("install heplab[analysis] for the CPU fit backend") from exc
    values = np.asarray(model_spec.get("values", []), dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("fit observations must be a finite one-dimensional sample")
    if "weights" in model_spec and not np.all(np.asarray(model_spec["weights"]) == 1):
        raise ValueError("this unbinned model does not support weighted observations")
    low, high = map(float, model_spec.get("range", [70, 110]))
    if not np.isfinite([low, high]).all() or not low < high:
        raise ValueError("fit range must be finite and increasing")
    values = values[(values >= low) & (values <= high)]
    if len(values) < 10:
        raise ValueError("at least ten in-range observations required")

    def nll(mean, sigma, signal_fraction):
        density = mixture_density(values, mean, sigma, signal_fraction, (low, high))
        if not np.isfinite(density).all() or np.any(density <= 0):
            return float("inf")
        return float(-np.log(density).sum())

    fit = Minuit(
        nll, mean=float(np.median(values)), sigma=max((high - low) / 20, 0.01), signal_fraction=0.8
    )
    fit.limits["mean"] = (low, high)
    fit.limits["sigma"] = (max((high - low) * 1e-6, 1e-8), (high - low) / 2)
    fit.limits["signal_fraction"] = (0, 1)
    fit.errordef = Minuit.LIKELIHOOD
    fit.migrad(ncall=10000)
    fit.hesse()
    fmin = fit.fmin
    valid = bool(fit.valid and fmin.has_accurate_covar and not fmin.has_parameters_at_limit)
    return {
        "model": "gaussian_plus_uniform",
        "success": valid,
        "validation": "unvalidated",
        "values": fit.values.to_dict(),
        "errors": fit.errors.to_dict(),
        "covariance": np.asarray(fit.covariance).tolist() if fit.covariance is not None else None,
        "n_events": len(values),
        "fit_range": [low, high],
        "objective": float(fit.fval),
        "edm": float(fmin.edm),
        "function_calls": fit.nfcn,
        "accurate_covariance": bool(fmin.has_accurate_covar),
        "parameters_at_limit": bool(fmin.has_parameters_at_limit),
        "message": (
            "Normalized teaching model; detector/radiative physics and coverage require validation."
        ),
    }
