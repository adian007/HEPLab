"""Verify preserved CMS geometry and independent navigation evidence.

This checks artifact integrity and internally consistent acceptance counts. It
does not rerun CMSSW/Geant4, clear geometry conflicts, or validate transport.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "artifacts/cms/geometry/export-2016-retry1"
COMPARISON = ROOT / "artifacts/cms/geometry/geant4-navigation-comparison-2026-10-28"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    run = load(EXPORT / "run.json")
    for relative, expected in run["artifacts"].items():
        actual = hashlib.sha256((EXPORT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"M0 artifact hash mismatch: {relative}")

    requirement_register = load(ROOT / "docs/engineering/requirements.json")
    geometry_requirement = next(
        row
        for row in requirement_register["requirements"]
        if row["id"] == "TRANSPORT-002"
    )
    assert geometry_requirement["status"] == "verified"
    assert any(
        item["record"]
        == "../../artifacts/cms/geometry/geant4-navigation-comparison-2026-10-28/validation.json"
        for item in geometry_requirement["evidence"]
    )

    summary = load(COMPARISON / "summary.json")
    validation = load(COMPARISON / "validation.json")
    comparison = load(COMPARISON / "comparison.json")
    assert run["status"] == "exported_and_reference_navigated"
    assert run["material_transport_status"] == "not yet validated"
    assert validation["execution"] == "passed"
    assert validation["physics_acceptance"] == "blocked"
    assert summary == validation["summary"] == comparison["summary"]
    assert summary["candidates"] == len(comparison["cases"]) == 146
    assert summary["rays_per_backend"] == 2_628
    assert summary["completed_backend_traces"] == 5_256
    assert summary["length_accounting_failures"] == 0
    assert summary["cross_backend_material_path_failure_rays"] == 38
    assert summary["cross_backend_material_path_failure_cases"] == 9
    assert summary["forward_reverse_failures"] == {"geant4": 510, "root": 478}
    assert summary["world_size_invariance_failures"] == 0
    assert summary["transport_clearances"] == 0
    assert all(not case["transport_cleared"] for case in comparison["cases"])
    print(
        "PASS: M0 hashes verified; M1 evidence is complete and internally "
        "consistent, with physics acceptance correctly blocked."
    )
    print(
        f"M1: {summary['candidates']} candidates, "
        f"{summary['completed_backend_traces']} traces, "
        f"{summary['cross_backend_material_path_failure_rays']} material-path "
        "disagreements, 0 transport clearances."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
