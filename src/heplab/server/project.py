"""Public project overview and evidence payloads.

Shared by the FastAPI routes and the desktop worker so the website and the
desktop app show identical data.
"""

# Display strings stay on one line each.
# ruff: noqa: E501

from __future__ import annotations

import json


def overview() -> dict:
    """Public, read-only status summary for the project overview website."""
    return {
        "name": "HEPLab",
        "version": "0.1.0.dev0",
        "stage": "EARLY IMPLEMENTATION",
        "license": "Apache-2.0",
        "repository": "https://github.com/adian007/QuantumArtGenerator-Cybersecurity",
        "desktop_status": "Desktop app planned · not yet distributed",
        "capabilities": [
            {
                "id": "data",
                "name": "CMS Open Data",
                "status": "foundations",
                "detail": "Versioned manifests, readers, certification, cache and provenance.",
                "href": "docs/engineering/02-data-supply.md",
            },  # noqa: E501
            {
                "id": "simulation",
                "name": "Local simulation",
                "status": "working-increment",
                "detail": "Reference bench, Rust engine, and native PYTHIA8/DELPHES runtime.",
                "href": "docs/engineering/sim-runtime.md",
            },  # noqa: E501
            {
                "id": "analysis",
                "name": "Analysis workflow",
                "status": "early-implementation",
                "detail": "Schemas, readers, processors, statistics and immutable artifacts.",
                "href": "docs/engineering/01-architecture.md",
            },  # noqa: E501
            {
                "id": "evidence",
                "name": "Validation evidence",
                "status": "in-progress",
                "detail": "Smoke evidence is distinct from independent physics validation.",
                "href": "docs/engineering/14-verification.md",
            },  # noqa: E501
        ],
        "stack": [
            {"name": "Python 3.12", "role": "Application services, CLI and data workflows"},
            {"name": "Rust + PyO3", "role": "Numerical engine and Python integration"},
            {
                "name": "PYTHIA8 + DELPHES",
                "role": "Optional native collision generation and fast simulation",
            },  # noqa: E501
            {"name": "React + TypeScript", "role": "Public project overview website"},
        ],
        "evidence": [],
        "roadmap": [
            {
                "phase": "FOUNDATIONS",
                "name": "Contracts & numerical core",
                "status": "IN PROGRESS",
                "detail": "Versioned schemas, requirements, numerical references, and Rust/PyO3 integration.",
            },  # noqa: E501
            {
                "phase": "DATA",
                "name": "Trustworthy data path",
                "status": "IN PROGRESS",
                "detail": "Certification, exact ranges, bounded caching, integrity evidence and offline replay.",
            },  # noqa: E501
            {
                "phase": "SIMULATION",
                "name": "Generation & detector response",
                "status": "IN PROGRESS",
                "detail": "Pinned native runtime and scoped reference bench; independent validation remains open.",
            },  # noqa: E501
            {
                "phase": "RELEASE",
                "name": "Desktop distribution",
                "status": "PLANNED",
                "detail": "Desktop shell, packaged service, installers, signing, updates and supported runtime matrix.",
            },  # noqa: E501
        ],
    }


def evidence() -> dict:
    """Small public evidence excerpt; detailed payloads remain in the repo."""
    from ..physics.calibration import REFERENCE

    silicon = json.loads((REFERENCE / "silicon-calibration.json").read_text(encoding="utf8"))
    field = json.loads((REFERENCE / "cms-field-validation.json").read_text(encoding="utf8"))
    return {
        "silicon": {
            "id": silicon["id"],
            "scope": silicon["scope"],
            "source_url": silicon["source_url"],
            "source_sha256": silicon["source_sha256"],
            "heldout_errors": silicon["heldout_errors"],
            "max_abs_relative_error": silicon["max_abs_relative_error"],
            "acceptance": silicon["acceptance"],
            "status": silicon["status"],
        },
        "cms_field": {
            "model": field["model"],
            "reference_rows": field["reference_rows"],
            "tracker_rows": field["tracker_rows"],
            "max_vector_error_t": field["max_vector_error_t"],
            "rms_vector_error_t": field["rms_vector_error_t"],
            "gate_max_vector_error_t": field["gate_max_vector_error_t"],
            "passed": field["passed"],
            "scope": field["scope"],
            "full_map_transport": field["full_map_transport"],
        },
    }
