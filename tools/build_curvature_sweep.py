"""Build a deterministic, provenance-bearing magnetic curvature example."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from heplab.physics.constants import constants_record
from heplab.physics.curvature import curvature_sweep

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src/heplab/data/reference/curvature-sweep-v1.json"
SOURCE_FILES = (
    "src/heplab/physics/constants.py",
    "src/heplab/physics/reference.py",
    "src/heplab/physics/cms_field.py",
    "src/heplab/physics/curvature.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    result = curvature_sweep()
    payload = {
        "schema": "heplab-curvature-sweep-report-v1",
        "classification": "educational software-model comparison; not detector validation",
        "constants": constants_record(),
        "source_sha256": {name: digest(ROOT / name) for name in SOURCE_FILES},
        "result": result,
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Built {OUTPUT.relative_to(ROOT)} from {len(SOURCE_FILES)} hashed source files")


if __name__ == "__main__":
    main()
