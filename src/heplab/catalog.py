"""Shared catalog authority for CLI, readers, notebooks and API."""

from __future__ import annotations

import os
from pathlib import Path

import yaml


def manifests_dir() -> Path:
    if os.environ.get("HEPLAB_MANIFEST_DIR"):
        return Path(os.environ["HEPLAB_MANIFEST_DIR"])
    repository = Path(__file__).resolve().parents[2] / "manifests/datasets"
    return repository if repository.is_dir() else Path(__file__).parent / "data/manifests"


def read_manifest(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"manifest {path} must be a mapping")
    return value


def list_datasets(directory: Path | None = None):
    for path in sorted((directory or manifests_dir()).glob("*.yaml")):
        yield read_manifest(path), path


def get(dataset: str, directory: Path | None = None) -> tuple[dict, Path]:
    matches = [
        (value, path)
        for value, path in list_datasets(directory)
        if dataset
        in (value.get("name"), value.get("dataset_id"), path.stem, *value.get("aliases", []))
    ]
    if len(matches) != 1:
        raise KeyError(f"dataset {dataset!r} {'is ambiguous' if matches else 'not found'}")
    return matches[0]
