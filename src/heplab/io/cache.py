"""Immutable chunk transactions with content hashes and exact source coverage."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .provenance import config_hash, file_hash

CACHE_VERSION = 2


def cache_key(dataset: str, branches: frozenset[str], schema_version: int, **identity) -> str:
    return config_hash(
        {
            "dataset": dataset,
            "branches": sorted(branches),
            "schema": schema_version,
            "cache": CACHE_VERSION,
            **identity,
        }
    )


def cache_root() -> Path:
    return Path(os.environ.get("HEPLAB_CACHE_DIR", str(Path.home() / ".cache/heplab")))


def _directory(key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("cache keys must be SHA-256 hex digests")
    root = cache_root().resolve()
    target = root / key
    if target.is_symlink() or target.resolve().parent != root:
        raise ValueError("cache path escapes its root")
    return target


def _sync(path: Path):
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def open_cached(key: str, *, expected: dict | None = None) -> list[dict]:
    directory = _directory(key)
    marker = directory / "commit.json"
    if marker.is_symlink() or not marker.is_file():
        raise FileNotFoundError(f"no verified committed chunk for {key}")
    descriptor = json.loads(marker.read_text(encoding="utf-8"))
    if descriptor.get("cache_version") != CACHE_VERSION or descriptor.get("key") != key:
        raise ValueError("cache commit identity is invalid")
    if expected is not None and descriptor.get("source") != expected:
        raise ValueError("cache coverage/source descriptor differs from request")
    name = descriptor.get("payload")
    if name not in {"events.parquet", "events.json"}:
        raise ValueError("invalid cache payload name")
    payload = directory / name
    if payload.is_symlink() or payload.resolve().parent != directory.resolve():
        raise ValueError("cache payload escapes its directory")
    if file_hash(payload) != descriptor["payload_sha256"]:
        raise ValueError("cache payload checksum mismatch")
    if name.endswith("parquet"):
        import pyarrow.parquet as pq

        events = pq.read_table(payload).to_pylist()
    else:
        events = json.loads(payload.read_text(encoding="utf-8"))
    if not isinstance(events, list) or len(events) != descriptor["rows"]:
        raise ValueError("cache row count is invalid")
    if config_hash({"events": events}) != descriptor["events_sha256"]:
        raise ValueError("cache normalized event checksum mismatch")
    return events


def write_json_events(key: str, events: list[dict], *, descriptor: dict | None = None) -> Path:
    """Publish a complete staged directory once; conflicting writers are rejected."""
    target = _directory(key)
    root = target.parent
    root.mkdir(parents=True, exist_ok=True)
    source = descriptor or {}
    config_hash({"events": events, "source": source})
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
    try:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            payload = stage / "events.json"
            payload.write_text(json.dumps(events, allow_nan=False), encoding="utf-8")
            normalized = events
        else:
            payload = stage / "events.parquet"
            table = pa.Table.from_pylist(events)
            normalized = table.to_pylist()
            pq.write_table(table, payload, compression="zstd")
        _sync(payload)
        commit = {
            "cache_version": CACHE_VERSION,
            "key": key,
            "source": source,
            "rows": len(events),
            "payload": payload.name,
            "payload_sha256": file_hash(payload),
            "events_sha256": config_hash({"events": normalized}),
        }
        marker = stage / "commit.json"
        marker.write_text(json.dumps(commit, sort_keys=True, allow_nan=False), encoding="utf-8")
        _sync(marker)
        try:
            os.rename(stage, target)
        except OSError:
            if not target.is_dir():
                raise
            previous = open_cached(key, expected=source)
            if config_hash({"events": previous}) != commit["events_sha256"]:
                raise ValueError(
                    "CacheConflict: different content for the same chunk identity"
                ) from None
        return target / payload.name
    finally:
        if stage.exists() and stage.resolve().parent == root and stage.name.startswith(".stage-"):
            shutil.rmtree(stage)
