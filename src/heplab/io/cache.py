"""Immutable chunk transactions with content hashes and exact source coverage."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
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


def quarantine(key: str) -> Path | None:
    """Move a damaged cache entry aside so the chunk can be re-read; keeps it for diagnosis."""
    target = _directory(key)
    if not target.is_dir():
        return None
    destination = target.with_name(f".quarantine-{key}-{os.getpid()}-{time.time_ns()}")
    os.rename(target, destination)
    return destination


def source_integrity_record(source_id: str, declared: dict, size_bytes: int) -> dict | None:
    """Return a matching previously verified source receipt, if one is intact."""
    if not re.fullmatch(r"[0-9a-f]{64}", source_id):
        raise ValueError("source IDs must be SHA-256 hex digests")
    root = cache_root().resolve()
    directory = root / ".integrity"
    receipt = directory / f"{source_id}.json"
    if directory.is_symlink() or receipt.is_symlink() or not receipt.is_file():
        return None
    if receipt.resolve().parent != directory.resolve():
        raise ValueError("source integrity receipt escapes its directory")
    try:
        value = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        value.get("source_id") == source_id
        and value.get("declared_checksum") == declared
        and value.get("size_bytes") == size_bytes
        and value.get("verified") is True
        and value.get("method") in {"local_bytes", "remote_digest", "remote_stream"}
    ):
        return value
    return None


def record_source_integrity(source_id: str, declared: dict, size_bytes: int, method: str) -> dict:
    """Atomically retain a successful source checksum verification receipt."""
    if method not in {"local_bytes", "remote_digest", "remote_stream"}:
        raise ValueError("unsupported source integrity method")
    root = cache_root().resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = root / ".integrity"
    if directory.is_symlink():
        raise ValueError("source integrity directory cannot be a symlink")
    directory.mkdir(exist_ok=True)
    receipt = directory / f"{source_id}.json"
    if receipt.is_symlink() or receipt.resolve().parent != directory.resolve():
        raise ValueError("source integrity receipt escapes its directory")
    value = {
        "source_id": source_id,
        "declared_checksum": declared,
        "size_bytes": size_bytes,
        "verified": True,
        "method": method,
        "verified_at": time.time(),
    }
    fd, name = tempfile.mkstemp(prefix=".verify-", dir=directory)
    stage = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage, receipt)
    finally:
        stage.unlink(missing_ok=True)
    return value


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
