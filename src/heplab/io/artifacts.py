"""Atomic immutable artifact files and child creation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .provenance import config_hash


def publish(path: str | Path, value: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    config_hash(value)
    data = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode("utf8")
    fd, name = tempfile.mkstemp(prefix=".artifact-", dir=target.parent)
    stage = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link atomically creates a new name and cannot replace an existing parent.
        try:
            os.link(stage, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError(f"immutable artifact already exists: {target}") from None
        return target
    finally:
        stage.unlink(missing_ok=True)
