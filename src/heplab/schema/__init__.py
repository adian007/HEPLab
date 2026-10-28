"""Unified event schema — the keystone (ADR-0003).

One versioned event model shared by real CMS data (NanoAOD, AOD) and locally
simulated events (DELPHES). Readers (``heplab.readers``) are the only code
allowed to know native formats; analyses consume only this schema. Closure
comparisons (data vs sim) are only meaningful because both sides normalize to
what is defined here.
"""

from .model import (
    ALL,
    ELECTRON,
    EVENT_INFO,
    GEN_PARTICLE,
    JET,
    MET,
    MUON,
    PHOTON,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    TRIGGER,
    CollectionSpec,
    export,
)

__all__ = [
    "ALL",
    "CollectionSpec",
    "ELECTRON",
    "EVENT_INFO",
    "GEN_PARTICLE",
    "JET",
    "MET",
    "MUON",
    "PHOTON",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "TRIGGER",
    "export",
]
