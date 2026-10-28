"""Independent scalar reference for the bounded thin-slab and electronics models."""

from __future__ import annotations

import math
from dataclasses import asdict

from .reference import FourVector, TrackState, addressed_normal, propagate_uniform_bz


def interact(state, slab, address):
    expected = {
        "id",
        "thickness_m",
        "radiation_length_m",
        "stopping_power_gev_per_m",
        "min_beta_gamma",
        "max_beta_gamma",
        "scatter",
    }
    if set(slab) != expected or type(slab["scatter"]) is not bool:
        raise ValueError("invalid slab fields")
    if not isinstance(slab["id"], str) or not 1 <= len(slab["id"].encode("utf8")) <= 128:
        raise ValueError("invalid material ID")
    t, x0, loss, low, high = (
        slab[k]
        for k in (
            "thickness_m",
            "radiation_length_m",
            "stopping_power_gev_per_m",
            "min_beta_gamma",
            "max_beta_gamma",
        )
    )
    if not all(math.isfinite(v) for v in (t, x0, loss, low, high)):
        raise ValueError("nonfinite material parameters")
    if t < 0 or x0 <= 0 or loss < 0 or low <= 0 or high < low:
        raise ValueError("invalid material parameters")
    p4 = state.momentum
    mass, p = p4.physical_mass, p4.momentum
    if mass < 0.1 or abs(state.charge) != 1 or p <= 0 or not low <= p / mass <= high:
        raise ValueError("outside heavy-particle stopping-power domain")
    deposit = t * loss
    if deposit > 0.1 * (p4.energy - mass):
        raise ValueError("thin-step loss exceeds 10% of kinetic energy")
    energy = p4.energy - deposit
    remaining = math.sqrt((energy - mass) * (energy + mass))
    if remaining / mass < low:
        raise ValueError("step exits stopping-power validity range")
    theta = 0.0
    if slab["scatter"] and t > 0:
        fraction = t / x0
        if not 0.001 <= fraction <= 0.1:
            raise ValueError("outside Highland thickness domain")
        theta = (
            0.0136 / (p * p / p4.energy) * math.sqrt(fraction) * (1 + 0.038 * math.log(fraction))
        )
        if theta > 0.2:
            raise ValueError("small-angle scattering domain exceeded")
    u = (p4.px / p, p4.py / p, p4.pz / p)
    axis = (0, 0, 1) if abs(u[2]) < 0.9 else (1, 0, 0)

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    v = cross(u, axis)
    norm = math.sqrt(sum(x * x for x in v))
    v = tuple(x / norm for x in v)
    w = cross(u, v)
    rng = {**address, "model_id": "thin-slab-highland-v1"}
    a = theta * addressed_normal(**{**rng, "stage_id": slab["id"] + ".scatter_x"}) if theta else 0
    b = theta * addressed_normal(**{**rng, "stage_id": slab["id"] + ".scatter_y"}) if theta else 0
    d = tuple(x + a * y + b * z for x, y, z in zip(u, v, w, strict=True))
    norm = math.sqrt(sum(x * x for x in d))
    middle = propagate_uniform_bz(state, t / 2, 0)
    moved = TrackState(
        middle.position,
        FourVector(energy, *(remaining * x / norm for x in d)),
        middle.charge,
        middle.time_ns,
    )
    final = propagate_uniform_bz(moved, t / 2, 0)
    return {
        "state": asdict(final),
        "deposit_gev": deposit,
        "theta0_rad": theta,
        "energy_residual_gev": p4.energy - final.momentum.energy - deposit,
        "model": "thin-slab-highland-v1",
        "validation": "educational_unvalidated",
        "material_id": slab["id"],
        "momentum_exchange": "untracked medium recoil; energy transfer is continuous loss",
    }


def digitize(deposit, config, address):
    if set(config) != {
        "gain_adc_per_gev",
        "pedestal_adc",
        "noise_sigma_adc",
        "threshold_adc",
        "saturation_adc",
    }:
        raise ValueError("invalid electronics fields")
    gain, pedestal, noise, threshold, saturation = (
        config[k]
        for k in (
            "gain_adc_per_gev",
            "pedestal_adc",
            "noise_sigma_adc",
            "threshold_adc",
            "saturation_adc",
        )
    )
    if not all(math.isfinite(x) for x in (deposit, gain, pedestal, noise, threshold, saturation)):
        raise ValueError("nonfinite electronics parameters")
    if (
        deposit < 0
        or gain <= 0
        or pedestal < 0
        or noise < 0
        or threshold < 0
        or not threshold < saturation <= 16777215
    ):
        raise ValueError("invalid electronics parameters")
    analog = (
        deposit * gain
        + pedestal
        + noise
        * addressed_normal(
            **{**address, "model_id": "deposit-electronics-v1", "stage_id": "channel_noise"}
        )
    )
    if not math.isfinite(analog):
        raise ValueError("nonfinite analog signal")
    accepted = analog >= threshold
    return {
        "adc": math.floor(max(0, min(saturation, analog))) if accepted else None,
        "accepted": accepted,
        "saturated": analog > saturation,
        "analog_adc": analog,
        "deposit_gev": deposit,
        "model": "deposit-electronics-v1",
        "validation": "educational_unvalidated",
    }
