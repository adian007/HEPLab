"""Analytic, float64 reference algorithms described in the engineering handbook.

Units are GeV, metres, nanoseconds, tesla and elementary positive charge.
Boosts are passive; fields are axial and uniform; transport is in vacuum.
Random draws use versioned SHA-256 addresses and are intended as a portable
reference, not a high-throughput event generator.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from bisect import bisect_right
from dataclasses import dataclass

C_METRES_PER_NS = 0.299792458
CURVATURE_GEV_T_METRES = 0.299792458
RNG_VERSION = "heplab-sha256-address-v1"


class NumericalDomainError(ValueError):
    """An input or computed result is outside the declared numerical domain."""


def _finite(*values: float) -> None:
    if not all(math.isfinite(value) for value in values):
        raise NumericalDomainError("all numerical values must be finite")


def wrap_phi(angle: float) -> float:
    """Map a finite angle to [-pi, pi); positive pi maps to negative pi."""
    _finite(angle)
    return (angle + math.pi) % math.tau - math.pi


@dataclass(frozen=True)
class FourVector:
    """Cartesian four-vector with (+,-,-,-) metric and nonnegative energy."""

    energy: float
    px: float
    py: float
    pz: float

    def __post_init__(self) -> None:
        _finite(self.energy, self.px, self.py, self.pz)
        if self.energy < 0:
            raise NumericalDomainError("energy must be nonnegative")

    @classmethod
    def from_pt_eta_phi_mass(cls, pt: float, eta: float, phi: float, mass: float) -> FourVector:
        _finite(pt, eta, phi, mass)
        if pt < 0 or mass < 0:
            raise NumericalDomainError("transverse momentum and mass must be nonnegative")
        try:
            pz = pt * math.sinh(eta)
        except OverflowError as exc:
            raise NumericalDomainError("pseudorapidity overflows the supported domain") from exc
        px, py = pt * math.cos(phi), pt * math.sin(phi)
        return cls(math.hypot(pt, pz, mass), px, py, pz)

    @property
    def momentum(self) -> float:
        return math.hypot(self.px, self.py, self.pz)

    @property
    def mass_squared(self) -> float:
        # Squared components can overflow even when individual components are finite.
        e2 = self.energy * self.energy
        p2 = math.fsum((self.px * self.px, self.py * self.py, self.pz * self.pz))
        _finite(e2, p2)
        return e2 - p2

    @property
    def physical_mass(self) -> float:
        m2 = self.mass_squared
        tolerance = (
            64
            * sys.float_info.epsilon
            * max(self.energy * self.energy, self.momentum * self.momentum, 1.0)
        )
        if m2 < -tolerance:
            raise NumericalDomainError("a spacelike vector has no physical on-shell mass")
        return math.sqrt(max(0.0, m2))

    def __add__(self, other: FourVector) -> FourVector:
        if not isinstance(other, FourVector):
            return NotImplemented
        return FourVector(
            self.energy + other.energy,
            self.px + other.px,
            self.py + other.py,
            self.pz + other.pz,
        )

    def boost(self, beta: tuple[float, float, float]) -> FourVector:
        """Passive boost to a frame moving at beta, with c=1."""
        if len(beta) != 3:
            raise NumericalDomainError("a boost needs three velocity components")
        _finite(*beta)
        b2 = math.fsum(component * component for component in beta)
        if not math.isfinite(b2) or b2 >= 1:
            raise NumericalDomainError("boost speed must be strictly less than light speed")
        gamma = 1.0 / math.sqrt(1.0 - b2)
        projection = math.fsum((beta[0] * self.px, beta[1] * self.py, beta[2] * self.pz))
        coefficient = gamma * gamma / (gamma + 1) * projection - gamma * self.energy
        return FourVector(
            gamma * (self.energy - projection),
            self.px + coefficient * beta[0],
            self.py + coefficient * beta[1],
            self.pz + coefficient * beta[2],
        )


def addressed_uniform(
    master_seed: int,
    event_key: str,
    object_id: int,
    stage_id: str,
    *,
    counter: int = 0,
    correlation_group: str = "nominal",
    model_id: str = "reference",
) -> float:
    """Return an order-independent uniform in the open interval (0, 1).

    JSON UTF-8 bytes with sorted keys, compact separators and ASCII escapes
    define the cross-language address. Do not change this encoding under v1.
    """
    for name, value in (
        ("master_seed", master_seed),
        ("object_id", object_id),
        ("counter", counter),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**53 - 1:
            raise NumericalDomainError(f"{name} must be an integer in [0, 2^53-1]")
    if not all(
        isinstance(value, str) and value
        for value in (event_key, stage_id, correlation_group, model_id)
    ):
        raise NumericalDomainError("random address labels must be nonempty strings")
    address = {
        "algorithm": RNG_VERSION,
        "master_seed": master_seed,
        "model_id": model_id,
        "event_key": event_key,
        "object_id": object_id,
        "stage_id": stage_id,
        "correlation_group": correlation_group,
        "counter": counter,
    }
    encoded = json.dumps(address, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(encoded.encode("utf-8")).digest()
    bits = int.from_bytes(digest[:8], "big") >> 11
    # The upper midpoint can round to one in float64; cap at the nearest interior value.
    return min(math.nextafter(1.0, 0.0), max(math.ulp(0.0), (bits + 0.5) / 2**53))


def addressed_normal(
    master_seed: int,
    event_key: str,
    object_id: int,
    stage_id: str,
    *,
    counter: int = 0,
    correlation_group: str = "nominal",
    model_id: str = "reference",
) -> float:
    """Standard normal from two addressed uniforms by the Box-Muller transform."""
    if isinstance(counter, bool) or not isinstance(counter, int) or not 0 <= counter < 2**52:
        raise NumericalDomainError("normal counter must be an integer in [0, 2^52)")
    options = {"correlation_group": correlation_group, "model_id": model_id}
    u1 = addressed_uniform(
        master_seed, event_key, object_id, stage_id, counter=2 * counter, **options
    )
    u2 = addressed_uniform(
        master_seed, event_key, object_id, stage_id, counter=2 * counter + 1, **options
    )
    return math.sqrt(-2 * math.log(u1)) * math.cos(math.tau * u2)


@dataclass(frozen=True)
class TrackState:
    """Vacuum particle state; position in metres, time in ns, charge in e."""

    position: tuple[float, float, float]
    momentum: FourVector
    charge: float
    time_ns: float = 0.0

    def __post_init__(self) -> None:
        if len(self.position) != 3:
            raise NumericalDomainError("position must have three components")
        _finite(*self.position, self.charge, self.time_ns)
        if self.time_ns < 0:
            raise NumericalDomainError("time must be nonnegative")
        _ = self.momentum.physical_mass


def propagate_uniform_bz(state: TrackState, path_length_m: float, bz_tesla: float) -> TrackState:
    """Exact vacuum trajectory in a uniform axial magnetic field.

    Lorentz convention: a positive charge initially along +x in positive Bz
    curves toward -y. This function models no material loss, scattering or decay.
    """
    _finite(path_length_m, bz_tesla)
    if path_length_m < 0:
        raise NumericalDomainError("forward propagation needs a nonnegative path length")
    p4 = state.momentum
    p = p4.momentum
    if p == 0 or not math.isfinite(p):
        raise NumericalDomainError("a stopped particle has no propagation direction")
    omega = -CURVATURE_GEV_T_METRES * state.charge * bz_tesla / p
    angle = omega * path_length_m
    _finite(angle)
    if abs(angle) < 1e-4:
        a2 = angle * angle
        sinc = 1 - a2 / 6 + a2 * a2 / 120
        cosc = angle * (0.5 - a2 / 24 + a2 * a2 / 720)
    else:
        sinc = math.sin(angle) / angle
        cosc = (1 - math.cos(angle)) / angle
    sine, cosine = math.sin(angle), math.cos(angle)
    x, y, z = state.position
    position = (
        x + path_length_m * (p4.px * sinc - p4.py * cosc) / p,
        y + path_length_m * (p4.px * cosc + p4.py * sinc) / p,
        z + path_length_m * p4.pz / p,
    )
    moved = FourVector(
        p4.energy,
        p4.px * cosine - p4.py * sine,
        p4.px * sine + p4.py * cosine,
        p4.pz,
    )
    time_ns = state.time_ns + path_length_m * p4.energy / (p * C_METRES_PER_NS)
    return TrackState(position, moved, state.charge, time_ns)


class WeightedHistogram:
    """Reference weighted histogram with flow bins and compensated sums.

    Index zero is underflow; index len(edges) is overflow. Interior bins are
    left inclusive and right exclusive, including overflow for the final edge.
    """

    def __init__(self, edges: tuple[float, ...]) -> None:
        if len(edges) < 2:
            raise NumericalDomainError("at least two histogram edges are required")
        _finite(*edges)
        if any(right <= left for left, right in zip(edges, edges[1:], strict=False)):
            raise NumericalDomainError("histogram edges must be strictly increasing")
        self.edges = tuple(edges)
        self._entries = [0] * (len(edges) + 1)
        self._sumw = [0.0] * (len(edges) + 1)
        self._sumw2 = [0.0] * (len(edges) + 1)
        self._comp_w = [0.0] * (len(edges) + 1)
        self._comp_w2 = [0.0] * (len(edges) + 1)

    @staticmethod
    def _neumaier(values: list[float], compensation: list[float], index: int, value: float):
        before = values[index]
        after = before + value
        _finite(after)
        if abs(before) >= abs(value):
            correction = (before - after) + value
        else:
            correction = (value - after) + before
        compensation[index] += correction
        _finite(compensation[index])
        values[index] = after

    def fill(self, value: float, weight: float = 1.0) -> None:
        _finite(value, weight, weight * weight)
        index = bisect_right(self.edges, value)
        # Preflight on copies makes a rejected overflow leave the histogram intact.
        sumw, cw = self._sumw.copy(), self._comp_w.copy()
        sumw2, cw2 = self._sumw2.copy(), self._comp_w2.copy()
        self._neumaier(sumw, cw, index, weight)
        self._neumaier(sumw2, cw2, index, weight * weight)
        self._sumw, self._comp_w, self._sumw2, self._comp_w2 = sumw, cw, sumw2, cw2
        self._entries[index] += 1

    def snapshot(self) -> dict:
        sumw = [value + comp for value, comp in zip(self._sumw, self._comp_w, strict=True)]
        sumw2 = [value + comp for value, comp in zip(self._sumw2, self._comp_w2, strict=True)]
        _finite(*sumw, *sumw2)
        return {
            "edges": list(self.edges),
            "entries_with_flow": self._entries.copy(),
            "sumw_with_flow": sumw,
            "sumw2_with_flow": sumw2,
        }

    def merge(self, other: WeightedHistogram) -> None:
        if self.edges != other.edges:
            raise NumericalDomainError("cannot merge histograms with different edges")
        sumw, cw = self._sumw.copy(), self._comp_w.copy()
        sumw2, cw2 = self._sumw2.copy(), self._comp_w2.copy()
        for index in range(len(sumw)):
            self._neumaier(sumw, cw, index, other._sumw[index])
            self._neumaier(sumw, cw, index, other._comp_w[index])
            self._neumaier(sumw2, cw2, index, other._sumw2[index])
            self._neumaier(sumw2, cw2, index, other._comp_w2[index])
        self._sumw, self._comp_w, self._sumw2, self._comp_w2 = sumw, cw, sumw2, cw2
        self._entries = [
            left + right for left, right in zip(self._entries, other._entries, strict=True)
        ]
