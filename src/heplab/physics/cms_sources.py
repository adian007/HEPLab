"""Pinned display assets, explicitly separated from transport conditions."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

DISPLAY = Path(__file__).resolve().parents[1] / "data/cms-display"


@lru_cache(maxsize=1)
def display_manifest() -> dict:
    return json.loads((DISPLAY / "manifest.json").read_text(encoding="utf8"))


def display_asset(layer_id: str) -> Path:
    suffix = next((s for s in ("-surface-outlines", "-surfaces") if layer_id.endswith(s)), "")
    identity = layer_id.removesuffix(suffix) if suffix else layer_id
    layer = next((x for x in display_manifest()["layers"] if x["id"] == identity), None)
    if layer is None:
        raise ValueError("unknown detector display layer")
    if suffix:
        layer = layer.get("surface_outlines" if suffix == "-surface-outlines" else "surfaces")
        if layer is None:
            raise ValueError("unknown detector display surface")
    path = DISPLAY / layer["file"]
    raw = path.read_bytes()
    if (
        len(raw) != layer["bytes"]
        or len(raw) != layer["vertices"] * 12
        or hashlib.sha256(raw).hexdigest() != layer["sha256"]
    ):
        raise ValueError("detector display asset failed integrity verification")
    return path
