"""Inspectable numerical reference for the planned Rust physics engine.

This module provides analytic primitives, not a calibrated detector simulator.
It is independent of the current legacy event readers and analysis contracts.
"""

from .reference import (
    FourVector,
    NumericalDomainError,
    TrackState,
    WeightedHistogram,
    addressed_normal,
    addressed_uniform,
    propagate_uniform_bz,
    wrap_phi,
)

__all__ = [
    "FourVector",
    "NumericalDomainError",
    "TrackState",
    "WeightedHistogram",
    "addressed_normal",
    "addressed_uniform",
    "propagate_uniform_bz",
    "wrap_phi",
]
