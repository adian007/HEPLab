"""Schema v1 collection definitions.

Field names follow docs/ARCHITECTURE.md §4. The mapping *from* native formats
(CMS NanoAOD branches, CMS AOD collections, DELPHES trees) lives in
``heplab.readers``; nothing in this module imports a native format or a heavy
dependency. Awkward-array builders arrive with the readers in Phase 1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

SCHEMA_NAME = "heplab-events"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CollectionSpec:
    """One physics-object collection in the internal event model.

    ``sim_only`` collections are produced by the simulation path (ADR-0004/0005)
    and absent from real-data chunks.
    """

    name: str
    fields: tuple[str, ...]
    sim_only: bool = False
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


MUON = CollectionSpec(
    "Muon",
    ("pt", "eta", "phi", "mass", "charge", "iso", "quality_flags"),
    description="muon candidates; iso = pfRelIso04-style relative isolation",
)
ELECTRON = CollectionSpec(
    "Electron",
    ("pt", "eta", "phi", "mass", "charge", "iso", "quality_flags"),
    description="electron candidates",
)
PHOTON = CollectionSpec(
    "Photon",
    ("pt", "eta", "phi", "mass", "iso", "has_pixel_seed"),
    description="photons; has_pixel_seed drives the H→γγ electron-veto (A4)",
)
JET = CollectionSpec("Jet", ("pt", "eta", "phi", "mass", "btag"), description="AK4 jets")
MET = CollectionSpec("MET", ("pt", "phi"), description="missing transverse momentum")
EVENT_INFO = CollectionSpec(
    "EventInfo",
    ("run", "luminosity_block", "event", "is_data", "weight"),
    description="scalar per-event data; weight is 1.0 for real data",
)
GEN_PARTICLE = CollectionSpec(
    "GenParticle",
    ("pdg_id", "status", "pt", "eta", "phi", "mass", "parent_idx"),
    sim_only=True,
    description="generator-level truth record (sim only)",
)
TRIGGER = CollectionSpec(
    "Trigger",
    ("names", "fired"),
    sim_only=True,
    description="trigger decision; simulation stores emulated decisions",
)

ALL: dict[str, CollectionSpec] = {
    c.name: c for c in (EVENT_INFO, MUON, ELECTRON, PHOTON, JET, MET, GEN_PARTICLE, TRIGGER)
}


def export() -> dict:
    """Machine-readable schema registry.

    Embedded in provenance stamps (ADR-0008) and asserted against by golden
    tests, so any schema change is visible in artifacts and CI.
    """
    return {
        "name": SCHEMA_NAME,
        "version": SCHEMA_VERSION,
        "collections": [c.to_dict() for c in ALL.values()],
    }
