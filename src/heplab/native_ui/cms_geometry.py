"""Validated display meshes from the pinned CMS outreach geometry snapshot.

The bundled iSpy-WebGL meshes are presentation geometry only.  This module is
kept outside the event/transport geometry code and never feeds physics
calculations.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

_DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "data/cms-display/manifest.json"
_EXPECTED_SCHEMA = "heplab-cms-display-v1"
_EXPECTED_COMMIT = "42b7d687344877f25213ec7650fc58148e87af2e"
_EXPECTED_LAYERS = frozenset({"pixel", "strips", "ecal", "hcal", "dt", "csc", "rpc"})
MUON_CHAMBER_LAYERS = frozenset({"dt", "csc", "rpc"})
_BOUND_TOLERANCE_M = 2e-6
_Bounds = tuple[tuple[float, float, float], tuple[float, float, float]]


@dataclass(frozen=True, slots=True)
class CMSLayerGeometry:
    """One CMS subsystem's validated, position-only display buffers."""

    positions: array
    outlines: array
    bounds: _Bounds

    @property
    def triangle_count(self) -> int:
        return len(self.positions) // 9

    @property
    def outline_segment_count(self) -> int:
        return len(self.outlines) // 6


def load_cms_geometry(
    manifest_path: Path | str | None = None,
) -> Mapping[str, CMSLayerGeometry]:
    """Load and cache the seven pinned CMS subsystem meshes.

    Each layer contains little-endian float32 XYZ triangle vertices and source
    outline line pairs.  The returned arrays are native-endian for direct Qt
    OpenGL upload.  The optional manifest path exists for validation and tests.
    """

    source = Path(manifest_path) if manifest_path is not None else _DEFAULT_MANIFEST
    return _load_cached(source.resolve())


def load_cms_manifest(manifest_path: Path | str | None = None) -> Mapping[str, Any]:
    """Return a validated copy of the display-source manifest for attribution."""

    source = Path(manifest_path) if manifest_path is not None else _DEFAULT_MANIFEST
    manifest = _read_manifest(source.resolve())
    return MappingProxyType(manifest)


@lru_cache(maxsize=4)
def _load_cached(manifest_path: Path) -> Mapping[str, CMSLayerGeometry]:
    manifest = _read_manifest(manifest_path)
    root = manifest_path.parent
    layers: dict[str, CMSLayerGeometry] = {}

    for entry in manifest["layers"]:
        layer_id = entry["id"]
        surfaces = entry.get("surfaces")
        source_outlines = entry.get("surface_outlines")
        if not isinstance(surfaces, dict) or not isinstance(source_outlines, dict):
            raise ValueError(f"CMS layer {layer_id!r} is missing curated surface buffers")

        positions = _read_buffer(root, surfaces, f"{layer_id} surfaces", multiple=3)
        if not positions or len(positions) % 9:
            raise ValueError(f"CMS layer {layer_id!r} surface vertices are not triangles")
        actual_bounds = _bounds(positions)
        declared_bounds = _parse_bounds(entry.get("bounds_m"), layer_id)
        _check_bounds(actual_bounds, declared_bounds, layer_id)

        # Chamber faces need their original iSpy edges for the thin outline pass.
        outline_record = entry if layer_id in MUON_CHAMBER_LAYERS else source_outlines
        outlines = _read_buffer(root, outline_record, f"{layer_id} outlines", multiple=2)
        if len(outlines) % 6:
            raise ValueError(f"CMS layer {layer_id!r} outline vertices are not line pairs")
        layers[layer_id] = CMSLayerGeometry(
            positions=positions,
            outlines=outlines,
            bounds=declared_bounds,
        )

    return MappingProxyType(layers)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load CMS display manifest from {path}: {exc}") from exc

    if not isinstance(value, dict) or value.get("schema") != _EXPECTED_SCHEMA:
        raise ValueError("unsupported CMS display geometry schema")
    if value.get("commit") != _EXPECTED_COMMIT:
        raise ValueError("CMS display geometry must use the pinned iSpy-WebGL commit")
    if value.get("source") != "https://github.com/cms-outreach/ispy-webgl":
        raise ValueError("unexpected CMS display geometry source")
    if value.get("license") != "MIT" or value.get("units") != "m":
        raise ValueError("CMS display geometry must retain its MIT license and metre units")
    if value.get("transport_compatible") is not False:
        raise ValueError("CMS display meshes must remain marked as display-only")
    entries = value.get("layers")
    if not isinstance(entries, list):
        raise ValueError("CMS display manifest layers must be a list")
    ids = [row.get("id") for row in entries if isinstance(row, dict)]
    if (
        len(ids) != len(entries)
        or len(ids) != len(_EXPECTED_LAYERS)
        or set(ids) != _EXPECTED_LAYERS
    ):
        raise ValueError(
            "CMS display manifest must define pixel, strips, ECAL, HCAL, DT, CSC and RPC"
        )
    return value


def _read_buffer(root: Path, record: dict[str, Any], label: str, multiple: int) -> array:
    name = record.get("file")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError(f"{label} has an invalid file name")
    try:
        raw = (root / name).read_bytes()
    except OSError as exc:
        raise ValueError(f"could not read {label} from {root / name}: {exc}") from exc

    expected_bytes = record.get("bytes")
    expected_vertices = record.get("vertices")
    if (
        not isinstance(expected_bytes, int)
        or not isinstance(expected_vertices, int)
        or expected_vertices < 0
        or expected_vertices % multiple
        or expected_bytes != expected_vertices * 3 * 4
        or len(raw) != expected_bytes
    ):
        raise ValueError(f"{label} byte or vertex count does not match the manifest")
    digest = record.get("sha256")
    if not isinstance(digest, str) or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{label} checksum does not match the manifest")

    values = array("f")
    values.frombytes(raw)
    if sys.byteorder == "big":
        values.byteswap()
    if len(values) != expected_vertices * 3:
        raise ValueError(f"{label} has an invalid float32 XYZ count")
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{label} contains a non-finite coordinate")
    return values


def _parse_bounds(value: Any, layer_id: str) -> _Bounds:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(not isinstance(point, list) or len(point) != 3 for point in value)
    ):
        raise ValueError(f"CMS layer {layer_id!r} has invalid bounds")
    bounds = tuple(tuple(float(axis) for axis in point) for point in value)
    if not all(math.isfinite(axis) for point in bounds for axis in point):
        raise ValueError(f"CMS layer {layer_id!r} bounds are not finite")
    if any(bounds[0][axis] > bounds[1][axis] for axis in range(3)):
        raise ValueError(f"CMS layer {layer_id!r} has inverted bounds")
    return bounds  # type: ignore[return-value]


def _bounds(values: array) -> _Bounds:
    low = [math.inf, math.inf, math.inf]
    high = [-math.inf, -math.inf, -math.inf]
    for index in range(0, len(values), 3):
        for axis in range(3):
            coordinate = values[index + axis]
            low[axis] = min(low[axis], coordinate)
            high[axis] = max(high[axis], coordinate)
    return tuple(low), tuple(high)  # type: ignore[return-value]


def _check_bounds(
    actual: _Bounds,
    declared: _Bounds,
    layer_id: str,
) -> None:
    # The manifest bounds describe the source subsystem mesh.  The curated
    # display-surface buffer is a subset, so its extent must be contained by
    # those bounds rather than exactly equal to them.
    for axis in range(3):
        actual_low, actual_high = actual[0][axis], actual[1][axis]
        source_low, source_high = declared[0][axis], declared[1][axis]
        if (
            actual_low < source_low - _BOUND_TOLERANCE_M
            or actual_high > source_high + _BOUND_TOLERANCE_M
        ):
            raise ValueError(f"CMS layer {layer_id!r} bounds do not match its surface mesh")

