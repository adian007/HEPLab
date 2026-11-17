"""Display-only iRPC chamber envelopes from a pinned CMSSW M17 snapshot.

This module intentionally has no import path into HEPLab physics or transport
geometry. The internal HPL/gas/readout stack is schematic because the pinned
M17 XML does not describe that assembly.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data/cms-display/irpc-m17.json"
TRIANGLES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (0, 2, 3),  # z- cap
    (4, 6, 5),
    (4, 7, 6),  # z+ cap
    (0, 4, 5),
    (0, 5, 1),  # +tangent side
    (1, 5, 6),
    (1, 6, 2),  # outer radial face
    (2, 6, 7),
    (2, 7, 3),  # -tangent side
    (3, 7, 4),
    (3, 4, 0),  # inner radial face
)


def _positive_number(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite positive number") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{label} must be a finite positive number")
    return result


def load_irpc_geometry(path: Path | None = None) -> dict:
    """Load the bundled display geometry JSON, or a caller-supplied copy."""
    source = Path(path) if path is not None else _DEFAULT_DATA
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not load iRPC display geometry from {source}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != "heplab-irpc-display-geometry-v1":
        raise ValueError("unsupported iRPC display geometry schema")
    _validate_data(value)
    return value


def _validate_data(data: dict) -> None:
    stations = data.get("placement", {}).get("stations")
    if not isinstance(stations, list) or len(stations) != 2:
        raise ValueError("iRPC display geometry must define RE3/1 and RE4/1")
    if {row.get("station") for row in stations} != {"RE3/1", "RE4/1"}:
        raise ValueError("iRPC station identities are invalid")
    if data.get("placement", {}).get("chambers_per_station_endcap") != 18:
        raise ValueError("iRPC geometry must define 18 chambers per station and endcap")
    for station in stations:
        values = station.get("values", {})
        for key in (
            "radial_center_m",
            "length_m",
            "inner_width_m",
            "outer_width_m",
            "depth_m",
            "z_center_m",
        ):
            if key not in values or "value" not in values[key]:
                raise ValueError(f"missing iRPC value {station['station']}.{key}")
            raw = float(values[key]["value"])
            if not math.isfinite(raw) or raw <= 0:
                raise ValueError(f"{station['station']}.{key} must be finite and positive")
        if values["outer_width_m"]["value"] < values["inner_width_m"]["value"]:
            raise ValueError(
                f"{station['station']} outer width must not be smaller than inner width"
            )
        for key in ("odd_copy_start_deg", "even_copy_start_deg"):
            if not all(
                math.isfinite(float(values[key][side])) for side in ("positive", "negative")
            ):
                raise ValueError(f"{station['station']}.{key} must be finite")
        for key in ("odd_copy_zoffset_m", "even_copy_zoffset_m"):
            if not math.isfinite(float(values[key]["value"])):
                raise ValueError(f"{station['station']}.{key} must be finite")
    components = data.get("stack", {}).get("components")
    expected_order = ["hpl", "gas", "hpl", "readout", "hpl", "gas", "hpl"]
    if (
        not isinstance(components, list)
        or [item.get("material") for item in components] != expected_order
    ):
        raise ValueError("iRPC schematic stack has an invalid HPL/gas/readout layer order")
    component_total = 0.0
    for component in components:
        component_total += _positive_number(component.get("depth_m"), "stack component depth")
        if not component.get("source") or not component.get("confidence"):
            raise ValueError(
                "every schematic stack dimension must include its source and confidence"
            )
    for station in stations:
        envelope = float(station["values"]["depth_m"]["value"])
        if component_total > envelope:
            raise ValueError("sourced schematic stack must fit inside the M17 frame envelope")
    if data.get("stack", {}).get("status") != "schematic_only":
        raise ValueError("the internal iRPC stack must remain labeled schematic_only")


def build_chambers(data: dict | None = None) -> list[dict]:
    """Build the 72 display-only trapezoid chamber records."""
    geometry = load_irpc_geometry() if data is None else data
    _validate_data(geometry)
    placement = geometry["placement"]
    step = math.radians(float(placement["sector_step_deg"]["value"]))
    base = math.radians(float(placement["base_rotation_deg"]["value"]))
    result: list[dict] = []
    for station_data in geometry["placement"]["stations"]:
        values = station_data["values"]
        station = station_data["station"]
        for endcap in (1, -1):
            placed = []
            for copy_number in range(1, 19):
                odd = copy_number % 2 == 1
                start = float(
                    values["odd_copy_start_deg"]["positive" if endcap > 0 else "negative"]
                    if odd
                    else values["even_copy_start_deg"]["positive" if endcap > 0 else "negative"]
                )
                local_phi = base + math.radians(start) + ((copy_number - 1) // 2) * step
                phi = local_phi if endcap > 0 else math.pi - local_phi
                phi = phi % (2 * math.pi)
                offset_key = "odd_copy_zoffset_m" if odd else "even_copy_zoffset_m"
                z_local = float(values["z_center_m"]["value"]) + float(values[offset_key]["value"])
                placed.append((phi, endcap * z_local, copy_number))
            placed.sort(key=lambda item: item[0])
            for index, (phi, z_m, copy_number) in enumerate(placed, start=1):
                endcap_name = "plus" if endcap > 0 else "minus"
                station_slug = station.lower().replace("/", "-")
                result.append(
                    {
                        "id": f"irpc-m17-{station_slug}-{endcap_name}-{index:02d}",
                        "name": f"M17 iRPC {station} {'+Z' if endcap > 0 else '-Z'} {index:02d}",
                        "station": station,
                        "ring": int(station_data["ring"]),
                        "chamber_index": index,
                        "endcap": endcap,
                        "z_m": z_m,
                        "phi_rad": phi,
                        "radial_center_m": float(values["radial_center_m"]["value"]),
                        "length_m": float(values["length_m"]["value"]),
                        "inner_width_m": float(values["inner_width_m"]["value"]),
                        "outer_width_m": float(values["outer_width_m"]["value"]),
                        "depth_m": float(values["depth_m"]["value"]),
                        "vertices": prism_vertices(
                            {
                                "z_m": z_m,
                                "phi_rad": phi,
                                "radial_center_m": float(values["radial_center_m"]["value"]),
                                "length_m": float(values["length_m"]["value"]),
                                "inner_width_m": float(values["inner_width_m"]["value"]),
                                "outer_width_m": float(values["outer_width_m"]["value"]),
                                "depth_m": float(values["depth_m"]["value"]),
                            }
                        ),
                        "native_copy_number": copy_number,
                        "display_only": True,
                    }
                )
    return result


def prism_vertices(
    chamber: dict,
    depth_m: float | None = None,
    offset_m: float = 0,
    thickness_scale: float = 1,
) -> list[tuple[float, float, float]]:
    """Return a radial trapezoid prism; corners 0–3 are the z− face."""
    scale = _positive_number(thickness_scale, "thickness_scale")
    depth = (
        _positive_number(chamber.get("depth_m") if depth_m is None else depth_m, "depth_m") * scale
    )
    z_center = float(chamber["z_m"]) + float(offset_m)
    phi = float(chamber["phi_rad"])
    radius = _positive_number(chamber["radial_center_m"], "radial_center_m")
    length = _positive_number(chamber["length_m"], "length_m")
    inner_width = _positive_number(chamber["inner_width_m"], "inner_width_m")
    outer_width = _positive_number(chamber["outer_width_m"], "outer_width_m")
    if not all(math.isfinite(number) for number in (z_center, phi)):
        raise ValueError("chamber position must be finite")
    radial = (math.cos(phi), math.sin(phi))
    tangent = (-math.sin(phi), math.cos(phi))
    inner_r, outer_r = radius - length / 2, radius + length / 2
    if inner_r <= 0:
        raise ValueError("chamber inner radial extent must be positive")
    corners_xy = (
        (
            inner_r * radial[0] + inner_width / 2 * tangent[0],
            inner_r * radial[1] + inner_width / 2 * tangent[1],
        ),
        (
            outer_r * radial[0] + outer_width / 2 * tangent[0],
            outer_r * radial[1] + outer_width / 2 * tangent[1],
        ),
        (
            outer_r * radial[0] - outer_width / 2 * tangent[0],
            outer_r * radial[1] - outer_width / 2 * tangent[1],
        ),
        (
            inner_r * radial[0] - inner_width / 2 * tangent[0],
            inner_r * radial[1] - inner_width / 2 * tangent[1],
        ),
    )
    first_face = corners_xy
    # Clockwise on z−; this yields outward winding with TRIANGLES above.
    ordered = first_face
    low, high = z_center - depth / 2, z_center + depth / 2
    return [(x, y, low) for x, y in ordered] + [(x, y, high) for x, y in ordered]


def build_chamber_prisms(
    chamber: dict, detail: bool = False, thickness_scale: float = 1
) -> list[dict]:
    """Create the chamber envelope, or a clearly schematic internal stack."""
    scale = _positive_number(thickness_scale, "thickness_scale")
    if not detail:
        return [
            {
                "component": "envelope",
                "vertices": prism_vertices(chamber, thickness_scale=scale),
                "material": "envelope",
            }
        ]

    components = _cached_stack_components()
    total_depth = _positive_number(chamber["depth_m"], "chamber depth") * scale
    component_depth = sum(layer["depth_m"] for layer in components) * scale
    if component_depth > total_depth:
        raise ValueError("source frame envelope is too small for the schematic stack")
    cursor = float(chamber["z_m"]) - component_depth / 2
    prisms = []
    for layer in components:
        thickness = layer["depth_m"] * scale
        offset = cursor + thickness / 2 - float(chamber["z_m"])
        prisms.append(
            {
                "component": layer["component"],
                "vertices": prism_vertices(chamber, depth_m=thickness, offset_m=offset),
                "material": layer["material"],
                "confidence": layer["confidence"],
                "source": layer["source"],
            }
        )
        cursor += thickness
    return prisms


@lru_cache(maxsize=1)
def _cached_stack_components() -> tuple[dict[str, Any], ...]:
    """Read and validate display stack metadata only once for repeated rendering."""
    data = load_irpc_geometry()
    return tuple(
        {
            "component": item["component"],
            "material": item["material"],
            "depth_m": float(item["depth_m"]),
            "confidence": item["confidence"],
            "source": item["source"],
        }
        for item in data["stack"]["components"]
    )
