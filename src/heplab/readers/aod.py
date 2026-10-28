"""CMS AOD reader for the classic Run-1 datasets (Phase 4–5, ADR-0003).

Scoped to what the classic analyses need (2011 DoubleMu spectrum, 2012
diphoton H→γγ): nested ``reco*`` collections are unwrapped into schema v1.
NanoAOD remains the primary input (ADR-0002); this reader exists so the
famous 2011/2012 masterclass datasets stay reachable.
"""

from __future__ import annotations


def read(*args, **kwargs):  # pragma: no cover - Phase 4–5
    raise NotImplementedError("AOD reader lands in Phase 4–5 — ADR-0003")
