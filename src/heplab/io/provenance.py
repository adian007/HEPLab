"""Strict computation identities and source snapshots; hashes do not prove correctness."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def config_hash(mapping: dict) -> str:
    """Stable hash of a (possibly nested) configuration mapping.

    Canonical JSON (sorted keys, compact separators) makes the hash independent
    of dict insertion order and formatting.
    """

    def check(value):
        if isinstance(value, dict):
            if not all(isinstance(key, str) for key in value):
                raise ValueError("canonical mapping keys must be strings")
            for child in value.values():
                check(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check(child)
        elif value is not None and not isinstance(value, (bool, int, float, str)):
            raise TypeError(f"unsupported canonical value: {type(value).__name__}")

    check(mapping)
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256_hex(canonical.encode())


@dataclass(frozen=True)
class ProvenanceStamp:
    schema_version: int
    git_sha: str
    config_sha256: str
    dataset_manifest_hash: str
    container_digest: str = ""
    file_checksums: tuple[str, ...] = ()
    source_tree_sha256: str = ""
    source_ranges: tuple[dict, ...] = ()
    certification_sha256: str = ""
    validation: str = "exploratory"

    @staticmethod
    def current_git_sha() -> str:
        """Return the current revision, or ``unknown`` outside a git checkout."""
        try:
            root = Path(__file__).resolve().parents[3]
            git_root = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if Path(git_root).resolve() != root:
                return "unknown-untracked-project"
            return subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    def to_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        """Content digest of the stamp itself."""
        return config_hash(self.to_dict())


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_snapshot(root: Path | None = None) -> str:
    """Hash source/config content including untracked edits, without scanning the drive."""
    if (
        root is None
        and not (Path(__file__).resolve().parents[3] / "src/heplab/__init__.py").is_file()
    ):
        package = Path(__file__).resolve().parent.parent
        return config_hash(
            {
                p.relative_to(package).as_posix(): file_hash(p)
                for p in sorted(package.rglob("*"))
                if p.is_file() and p.suffix in {".py", ".yaml", ".json"}
            }
        )
    root = root or Path(__file__).resolve().parents[3]
    paths: list[Path] = []
    for folder in ("src", "kernels/src", "kernels/physics-core", "contracts"):
        paths.extend(
            p
            for p in (root / folder).rglob("*")
            if p.is_file()
            and (p.suffix in {".py", ".rs", ".toml", ".yaml", ".json"} or p.name == "Cargo.lock")
            and "target" not in p.parts
        )
    paths.extend(
        root / p
        for p in (
            "pyproject.toml",
            "kernels/Cargo.toml",
            "kernels/Cargo.lock",
            "rust-toolchain.toml",
        )
        if (root / p).is_file()
    )
    return config_hash({p.relative_to(root).as_posix(): file_hash(p) for p in sorted(paths)})
