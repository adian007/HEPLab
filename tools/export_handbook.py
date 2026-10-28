"""Package handbook sources, local HTML, contracts and the numerical reference.

Run after the strict site build: python tools/export_handbook.py
Only explicit project directories are read; event data and installed packages
are excluded. The export contains design targets and scoped reference code.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if not (ROOT / ".cache/handbook-site/index.html").is_file():
        raise SystemExit("Build the documentation HTML before exporting the handbook")
    selected: dict[str, Path] = {}
    for name in ("README.md", "LICENSE", "mkdocs.yml", "pyproject.toml", "rust-toolchain.toml"):
        selected[name] = ROOT / name
    for folder in (
        "docs",
        "contracts",
        "tools",
        "src",
        "tests",
        "manifests",
        "kernels",
        "examples",
        "deploy",
        ".github",
    ):
        for path in sorted((ROOT / folder).rglob("*")):
            if (
                path.is_file()
                and not {"__pycache__", "target", "node_modules"}.intersection(path.parts)
                and path.suffix not in {".root", ".parquet", ".pyc"}
            ):
                selected[path.relative_to(ROOT).as_posix()] = path
    for name in ("test_physics_reference.py", "test_handbook_contracts.py"):
        selected[f"tests/{name}"] = ROOT / "tests" / name
    for path in sorted((ROOT / ".cache/handbook-site").rglob("*")):
        if path.is_file():
            selected["html/" + path.relative_to(ROOT / ".cache/handbook-site").as_posix()] = path
    manifest = {
        "scope": "Engineering specification, current Python/Rust source, contracts and local HTML",
        "not_included": (
            "Compiled native binaries, calibrated detector models, event caches or dependencies"
        ),
        "sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in sorted(selected.items())
        },
    }
    target = ROOT / "artifacts/heplab-engineering-handbook.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(selected.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
        archive.writestr("EXPORT-MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Export integrity check failed")
    print(f"Exported {len(selected)} files: {target} ({target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
