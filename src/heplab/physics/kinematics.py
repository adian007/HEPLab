"""Physics-level kinematic helpers shared by analyses and calibration code."""

from __future__ import annotations

from .reference import FourVector


def invariant_mass(first: dict, second: dict) -> float:
    """Return the physical invariant mass of two pt/eta/phi/mass records in GeV."""
    vectors = [
        FourVector.from_pt_eta_phi_mass(*(float(obj[key]) for key in ("pt", "eta", "phi", "mass")))
        for obj in (first, second)
    ]
    return (vectors[0] + vectors[1]).physical_mass
