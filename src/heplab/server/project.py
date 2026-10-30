"""Public project overview and evidence payloads.

Shared by the FastAPI routes and the desktop worker so the website and the
desktop app show identical data.
"""

from __future__ import annotations

import json
from pathlib import Path

# Display strings stay on one line each.
# ruff: noqa: E501

_CAPABILITY_FILE = Path(__file__).resolve().parents[1] / "data" / "project-capabilities.json"


def overview() -> dict:
    """Public, read-only status summary for the project overview website."""
    capabilities = json.loads(_CAPABILITY_FILE.read_text(encoding="utf8"))
    return {
        "name": "HEPLab",
        "version": "0.1.0.dev0",
        "stage": "EARLY IMPLEMENTATION",
        "license": "Apache-2.0",
        "repository": "https://github.com/adian007/HEPLab",
        "desktop_status": "Windows desktop build smoke-tested; no public installer is currently distributed.",
        "capabilities": [
            {key: item[key] for key in ("id", "name", "status", "detail", "href")}
            for item in capabilities
        ],
        "stack": [
            {"name": "Python 3.12", "role": "Application services, CLI and data workflows"},
            {"name": "Rust + PyO3", "role": "Numerical engine and Python integration"},
            {
                "name": "PYTHIA8 + DELPHES",
                "role": "Optional native collision generation and fast simulation",
            },  # noqa: E501
            {
                "name": "HEPLab Workbench",
                "role": "Local desktop interface with offline guided tour",
            },
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
