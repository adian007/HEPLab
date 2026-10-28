"""Reader registry — the only code allowed to know native event formats (ADR-0003).

Each reader normalizes one native format into ``heplab.schema`` v1 and is
locked by golden-file unit tests against tiny committed event samples.

- ``nanoaod`` — CMS Run 2 NanoAOD (primary input, flat branches)
- ``aod``     — CMS Run 1 AOD (classic 2011/2012 datasets, nested collections)
- ``delphes`` — DELPHES fast-simulation output (ADR-0004)
"""

from __future__ import annotations

READERS: dict[str, str] = {
    "nanoaod": "heplab.readers.nanoaod:read",
    "aod": "heplab.readers.aod:read",
    "delphes": "heplab.readers.delphes:read",
}

# Phase in which each reader is scoped.
PHASES: dict[str, str] = {"nanoaod": "Phase 1", "aod": "Phase 4–5", "delphes": "Phase 3"}


def get_reader(name: str):
    """Resolve a reader by format name."""
    if name not in READERS:
        raise KeyError(f"unknown reader '{name}' — known: {sorted(READERS)}")
    if name == "aod":
        raise NotImplementedError(
            "CMS AOD support is not implemented; use NanoAOD or DELPHES (ADR-0003)"
        )
    module_name, function_name = READERS[name].split(":")
    from importlib import import_module

    return getattr(import_module(module_name), function_name)
