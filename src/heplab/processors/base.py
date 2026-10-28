"""Processor protocol (Phase 2).

The coffea-backed implementation arrives with the first analysis; this module
fixes the contract early so analyses, closures, and the dashboard all target
the same interface.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Processor(Protocol):
    """Contract for analysis processors.

    Implementations must be source-agnostic (schema v1 in, artifacts out),
    chunk-parallel (coffea/Dask, ADR-0006), and must emit a provenance stamp
    with every artifact (ADR-0008).
    """

    name: str

    def select(self, chunk: Any) -> Any:
        """Return a boolean/integer selection mask over one schema-v1 chunk."""
        ...

    def produce(self, chunk: Any) -> dict[str, Any]:
        """Return artifacts (histograms, cutflow counts) for one chunk."""
        ...
