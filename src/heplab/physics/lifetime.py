"""A bounded single-muon proper-time survival teaching model.

This model propagates survival probability at fixed momentum. It does not
simulate atmospheric showers, muon energy loss, or decay daughter kinematics.
"""

from __future__ import annotations

import math

from .constants import (
    MUON_MASS_GEV,
    MUON_MEAN_LIFETIME_S,
    SPEED_OF_LIGHT_M_PER_S,
    constants_record,
)
from .reference import addressed_uniform

MODEL_ID = "muon-proper-time-survival-v1"


def _finite_nonnegative(name: str, value: float, *, allow_zero: bool = True) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if number < 0 or (not allow_zero and number == 0):
        qualifier = "positive" if not allow_zero else "nonnegative"
        raise ValueError(f"{name} must be {qualifier}")
    return number


def mean_decay_path_m(
    momentum_gev_c: float,
    *,
    mass_gev: float = MUON_MASS_GEV,
    mean_lifetime_s: float = MUON_MEAN_LIFETIME_S,
) -> float:
    """Compute beta-gamma c tau for a stable momentum and sourced constants."""
    momentum = _finite_nonnegative("momentum_gev_c", momentum_gev_c, allow_zero=False)
    mass = _finite_nonnegative("mass_gev", mass_gev, allow_zero=False)
    lifetime = _finite_nonnegative("mean_lifetime_s", mean_lifetime_s, allow_zero=False)
    length = (momentum / mass) * SPEED_OF_LIGHT_M_PER_S * lifetime
    if not math.isfinite(length) or length <= 0:
        raise ValueError("computed mean decay path is outside the supported numeric domain")
    return length


def survival_probability(momentum_gev_c: float, path_length_m: float) -> float:
    """Return analytic probability of surviving a path at fixed momentum."""
    path = _finite_nonnegative("path_length_m", path_length_m)
    return math.exp(-path / mean_decay_path_m(momentum_gev_c))


def decay_probability(momentum_gev_c: float, path_length_m: float) -> float:
    """Return the numerically stable complementary decay probability."""
    path = _finite_nonnegative("path_length_m", path_length_m)
    return -math.expm1(-path / mean_decay_path_m(momentum_gev_c))


def path_from_altitudes_m(
    production_altitude_m: float,
    detector_altitude_m: float = 0.0,
    zenith_angle_rad: float = 0.0,
) -> float:
    """Plane-parallel straight-path distance; no atmospheric transport is implied."""
    production = _finite_nonnegative("production_altitude_m", production_altitude_m)
    detector = _finite_nonnegative("detector_altitude_m", detector_altitude_m)
    zenith = _finite_nonnegative("zenith_angle_rad", zenith_angle_rad)
    if production <= detector:
        raise ValueError("production altitude must be above detector altitude")
    if zenith >= math.radians(75):
        raise ValueError("plane-parallel path model supports zenith angles below 75 degrees")
    return (production - detector) / math.cos(zenith)


def _wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> list[float]:
    fraction = successes / trials
    denominator = 1 + z * z / trials
    center = (fraction + z * z / (2 * trials)) / denominator
    half = z * math.sqrt(fraction * (1 - fraction) / trials + z * z / (4 * trials**2))
    half /= denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def run_survival_experiment(
    *,
    momentum_gev_c: float,
    path_length_m: float,
    seed: int,
    sample_size: int = 10_000,
    event_key: str = "muon-lifetime-experiment-v1",
) -> dict:
    """Compare the analytic survival probability with an address-seeded sample."""
    momentum = _finite_nonnegative("momentum_gev_c", momentum_gev_c, allow_zero=False)
    path = _finite_nonnegative("path_length_m", path_length_m)
    if type(seed) is not int or not 1 <= seed <= 900_000_000:
        raise ValueError("seed must be an integer in [1, 900000000]")
    if type(sample_size) is not int or not 100 <= sample_size <= 100_000:
        raise ValueError("sample_size must be an integer in [100, 100000]")
    if not isinstance(event_key, str) or not event_key or len(event_key) > 128:
        raise ValueError("event_key must be a nonempty string of at most 128 characters")

    mean_path = mean_decay_path_m(momentum)
    expected = survival_probability(momentum, path)
    survivors = 0
    for object_id in range(sample_size):
        uniform = addressed_uniform(
            seed,
            event_key,
            object_id,
            "proper_time",
            model_id=MODEL_ID,
        )
        sampled_decay_path = -mean_path * math.log(uniform)
        survivors += sampled_decay_path > path
    observed = survivors / sample_size
    return {
        "experiment": "muon-survival",
        "schema": "heplab-lifetime-result-v1",
        "data_kind": "seeded analytic teaching sample",
        "config": {
            "momentum_gev_c": momentum,
            "path_length_m": path,
            "seed": seed,
            "sample_size": sample_size,
            "rng_version": "heplab-sha256-address-v1",
        },
        "summary": {
            "mean_decay_path_m": mean_path,
            "expected_survival_probability": expected,
            "expected_decay_probability": -math.expm1(-path / mean_path),
            "observed_survivors": survivors,
            "observed_survival_probability": observed,
            "observed_decay_probability": 1 - observed,
            "survival_wilson_95_percent": _wilson_interval(survivors, sample_size),
        },
        "model_spec": {
            "schema": "heplab-model-spec-v1",
            "id": MODEL_ID,
            "version": 1,
            "name": "Single-muon proper-time survival at fixed momentum",
            "units": {"momentum": "GeV/c", "path": "m", "lifetime": "s"},
            "domain": {
                "particle": "muon",
                "momentum_gev_c": [momentum, momentum],
                "path_length_m": [0.0, path],
                "momentum_is_constant": True,
            },
            "assumptions": [
                "vacuum proper-time exponential with the 2025 PDG mean lifetime",
                "constant momentum and straight flight over the declared path",
                "one independent seeded decay-time draw per trial",
            ],
            "omitted_effects": [
                "atmospheric production spectrum and hadronic shower",
                "energy loss and scattering in air or detector material",
                "decay daughter kinematics and spin correlations",
            ],
            "validation": {
                "state": "analytic_reference_and_seeded_sampling",
                "scope": "survival law only; not an atmospheric shower or detector calibration",
            },
            "constants": constants_record(),
        },
        "validation": "analytic_reference_and_seeded_sampling",
    }
