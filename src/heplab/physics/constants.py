"""Versioned particle and unit constants used by the teaching models."""

from __future__ import annotations

from dataclasses import asdict, dataclass

CONSTANTS_ID = "pdg-2025"
CONSTANTS_SOURCE = "https://pdg.lbl.gov/2025/listings/rpp2025-list-muon.pdf"
CODATA_C_ID = "codata-exact-c"
CODATA_C_SOURCE = "https://physics.nist.gov/cgi-bin/cuu/Value?c"

SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
SPEED_OF_LIGHT_M_PER_NS = SPEED_OF_LIGHT_M_PER_S * 1e-9
CURVATURE_GEV_T_METRES = 0.299792458

MUON_MASS_GEV = 0.1056583755
MUON_MASS_UNCERTAINTY_GEV = 0.0000023e-3
MUON_MEAN_LIFETIME_S = 2.1969811e-6
MUON_MEAN_LIFETIME_UNCERTAINTY_S = 0.0000022e-6


@dataclass(frozen=True)
class PhysicalConstant:
    name: str
    value: float
    unit: str
    uncertainty: float | None
    source_id: str
    source_url: str


PHYSICAL_CONSTANTS = (
    PhysicalConstant(
        "muon_mass",
        MUON_MASS_GEV,
        "GeV/c^2",
        MUON_MASS_UNCERTAINTY_GEV,
        CONSTANTS_ID,
        CONSTANTS_SOURCE,
    ),
    PhysicalConstant(
        "muon_mean_lifetime",
        MUON_MEAN_LIFETIME_S,
        "s",
        MUON_MEAN_LIFETIME_UNCERTAINTY_S,
        CONSTANTS_ID,
        CONSTANTS_SOURCE,
    ),
    PhysicalConstant(
        "speed_of_light",
        SPEED_OF_LIGHT_M_PER_S,
        "m/s",
        0.0,
        CODATA_C_ID,
        CODATA_C_SOURCE,
    ),
    PhysicalConstant(
        "curvature_conversion",
        CURVATURE_GEV_T_METRES,
        "GeV/(c T m)",
        0.0,
        CODATA_C_ID,
        CODATA_C_SOURCE,
    ),
)


def constants_record() -> dict:
    """Return a fresh JSON-compatible snapshot for run provenance."""
    return {
        "id": CONSTANTS_ID,
        "source": CONSTANTS_SOURCE,
        "values": [asdict(value) for value in PHYSICAL_CONSTANTS],
    }
