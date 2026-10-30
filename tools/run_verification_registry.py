"""Run the review verification registry and emit current machine-readable evidence.

Run from any directory with the project's Python environment:

    python tools/run_verification_registry.py

The output is deliberately written to stdout so a passing result cannot be
mistaken for a checked-in, current scientific validation report.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/scientific-review/verification/registry.json"
CHECK_SCRIPT = ROOT / "docs/scientific-review/verification/independent_checks.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    process = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        observed = json.loads(process.stdout)
    except json.JSONDecodeError:
        observed = {"stdout": process.stdout[-8000:], "stderr": process.stderr[-8000:]}
    report = {
        "schema": "heplab-verification-run-v1",
        "registry_sha256": digest(REGISTRY),
        "registry": registry,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": Path(sys.executable).name,
        },
        "source_sha256": {
            "independent_checks.py": digest(CHECK_SCRIPT),
            "constants.py": digest(ROOT / "src/heplab/physics/constants.py"),
            "reference.py": digest(ROOT / "src/heplab/physics/reference.py"),
            "curvature.py": digest(ROOT / "src/heplab/physics/curvature.py"),
            "cms_field.py": digest(ROOT / "src/heplab/physics/cms_field.py"),
            "lifetime.py": digest(ROOT / "src/heplab/physics/lifetime.py"),
            "calibration.py": digest(ROOT / "src/heplab/physics/calibration.py"),
            "detector.py": digest(ROOT / "src/heplab/physics/detector.py"),
            "material.py": digest(ROOT / "src/heplab/physics/material.py"),
            "registry_runner.py": digest(Path(__file__).resolve()),
        },
        "status": "passed"
        if process.returncode == 0 and observed.get("all_checks_passed")
        else "failed",
        "return_code": process.returncode,
        "observed": observed,
        "stderr": process.stderr[-8000:],
        "interpretation": (
            "A passing run verifies only the named equations, integration comparisons, "
            "curvature/sagitta formula, table behavior, and RNG checks in the registry. "
            "It is not experimental detector validation."
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
