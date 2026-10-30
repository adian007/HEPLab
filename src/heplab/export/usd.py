"""OpenUSD export of workbench event displays.

Input is a workbench display payload — any JSON artifact produced by the local
workbench (``heplab-workbench-result-v2``, a stored per-event bench record, or
the ``muon_display`` overlay in a pythia run) — carrying ``tracks`` and
``geometry``. The stage mirrors what the 2D canvas draws:

- ``/detector`` one prim per guide surface (open tubes for cylinders, annular
  disks at their z plane), colored by subsystem;
- ``/tracks`` one linear ``BasisCurves`` per track, colored by charge, with the
  sampled points copied verbatim (metres, float64 rounded to float32 on write —
  a display interchange, not a precision channel);
- ``/crossings`` one ``UsdGeomPoints`` with every predicted surface crossing and
  its ``surface_id`` as a per-point primvar;
- ``/main_camera`` a Z-up framing camera so offline renderers start composed.

OpenUSD authoring and inspection here are CPU-only; viewing needs only OpenGL.
Units are metres and the up axis is Z, matching detector convention.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from ..io.provenance import config_hash

# Subsystem display colors (linear RGB) and transparency, chosen to read like
# the workbench canvas palette on both dark and light backdrops.
_SUBSYSTEM_STYLE = {
    "pixel": ((0.55, 0.35, 0.85), 0.65),
    "tracker-envelope": ((0.20, 0.65, 0.60), 0.10),
    "solenoid": ((0.45, 0.45, 0.48), 0.05),
}
_DEFAULT_STYLE = ((0.60, 0.60, 0.62), 0.35)
_CHARGE_COLORS = {
    1: (0.90, 0.25, 0.20),  # positive: red, CMS event-display convention
    -1: (0.25, 0.45, 0.95),  # negative: blue
}
_NEUTRAL_COLOR = (0.85, 0.75, 0.30)
_SEGMENTS = 48
_TRACK_WIDTH_M = 0.012
_CROSSING_WIDTH_M = 0.015
# Two authored framings: the whole modeled volume and a tracker close-up.
# Both look at the interaction point; Z stays up.
_CAMERAS = (
    ("main_camera", (18.0, -14.5, 9.0)),
    ("tracker_camera", (3.2, -2.6, 1.6)),
)


def _normalized_payload(result: dict) -> dict:
    if not isinstance(result, dict):
        raise ValueError("display payload must be a JSON object")
    tracks = result.get("tracks")
    geometry = result.get("geometry")
    if not isinstance(tracks, list) or not isinstance(geometry, dict):
        raise ValueError("expected a workbench display payload with 'tracks' and 'geometry'")
    surfaces = geometry.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise ValueError("display payload geometry carries no surfaces")
    usable = [
        track
        for track in tracks
        if isinstance(track, dict)
        and isinstance(track.get("points"), list)
        and len(track["points"]) >= 2
        and all(
            isinstance(point, list | tuple)
            and len(point) == 3
            and all(isinstance(v, int | float) and math.isfinite(v) for v in point)
            for point in track["points"]
        )
    ]
    if not usable:
        raise ValueError("display payload has no track with at least two finite 3D points")
    return {"tracks": usable, "geometry": geometry}


def _prim_name(surface_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(surface_id)).strip("_")
    if not name or not (name[0].isalpha() or name[0] == "_"):
        name = f"surface_{name or 0}"
    return name


def _ring(radius: float, segments: int) -> list[tuple[float, float]]:
    return [
        (
            radius * math.cos(2 * math.pi * i / segments),
            radius * math.sin(2 * math.pi * i / segments),
        )
        for i in range(segments)
    ]


def _tube_points(
    radius: float, half_length: float, segments: int
) -> list[tuple[float, float, float]]:
    ring = _ring(radius, segments)
    return [(x, y, -half_length) for x, y in ring] + [(x, y, half_length) for x, y in ring]


def _tube_topology(segments: int) -> tuple[list[int], list[int]]:
    counts: list[int] = []
    indices: list[int] = []
    for i in range(segments):
        j = (i + 1) % segments
        counts.append(4)
        indices.extend((i, j, segments + j, segments + i))
    return counts, indices


def _annulus_points(inner: float, outer: float, segments: int) -> list[tuple[float, float, float]]:
    points = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        cos, sin = math.cos(angle), math.sin(angle)
        points.append((outer * cos, outer * sin, 0.0))
        points.append((inner * cos, inner * sin, 0.0))
    return points


def _annulus_topology(segments: int) -> tuple[list[int], list[int]]:
    counts: list[int] = []
    indices: list[int] = []
    for i in range(segments):
        j = (i + 1) % segments  # modulo closes the ring at the last spoke
        counts.append(4)
        indices.extend((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    return counts, indices


def _extent(points) -> tuple[list[float], list[float]]:
    low = [min(point[axis] for point in points) for axis in range(3)]
    high = [max(point[axis] for point in points) for axis in range(3)]
    return low, high


def _look_at_matrix(eye, target, up) -> tuple[float, ...]:
    """Row-vector look-at basis (USD transforms row vectors): rows are the camera axes."""

    def subtract(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(a, b):
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def normalized(v):
        magnitude = math.sqrt(sum(component * component for component in v))
        if magnitude == 0:
            raise ValueError("degenerate camera direction")
        return tuple(component / magnitude for component in v)

    backward = normalized(subtract(eye, target))
    right = normalized(cross(up, backward))
    new_up = cross(backward, right)
    return (
        right[0],
        right[1],
        right[2],
        0.0,
        new_up[0],
        new_up[1],
        new_up[2],
        0.0,
        backward[0],
        backward[1],
        backward[2],
        0.0,
        eye[0],
        eye[1],
        eye[2],
        1.0,
    )


def export_event(result: dict, output: str | Path) -> dict:
    """Write a workbench display payload as an OpenUSD stage and verify it reopens."""
    payload = _normalized_payload(result)
    tracks, geometry = payload["tracks"], payload["geometry"]

    try:
        from pxr import Gf, Sdf, Usd, UsdGeom
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "USD export requires OpenUSD; install it with `pip install 'heplab[usd]'`"
        ) from exc

    output = Path(output)
    if output.suffix.lower() not in {".usd", ".usda"}:
        output = output.with_suffix(".usd")
    if output.exists():
        raise ValueError(f"USD output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    stage = Usd.Stage.CreateNew(str(output))
    if stage is None:
        raise ValueError(f"OpenUSD refused to create {output}")
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetMetadata(
        "customLayerData",
        {
            "heplabGeometryId": str(geometry.get("id", "unknown")),
            "heplabGeometrySha256": str(geometry.get("sha256", "")),
            "heplabEvent": int(result.get("event", 0) or 0),
            "heplabTrackCount": len(tracks),
            "heplabDisplay": str(result.get("display", ""))[:512],
            "heplabFieldModel": str(geometry.get("field", {}).get("model", "")),
        },
    )
    world = UsdGeom.Xform.Define(stage, "/World").GetPrim()
    stage.SetDefaultPrim(world)

    crossings: list[tuple[list[float], str]] = []
    UsdGeom.Xform.Define(stage, "/World/detector")
    for surface in geometry["surfaces"]:
        if not isinstance(surface, dict) or surface.get("kind") not in {"cylinder", "disk"}:
            continue
        color, opacity = _SUBSYSTEM_STYLE.get(str(surface.get("subsystem", "")), _DEFAULT_STYLE)
        name = _prim_name(surface.get("id", "surface"))
        path = f"/World/detector/{name}"
        if stage.GetPrimAtPath(path).IsValid():
            raise ValueError(f"duplicate detector surface name {name!r}")
        if surface["kind"] == "cylinder":
            points = _tube_points(
                float(surface["radius_m"]), float(surface["half_length_m"]), _SEGMENTS
            )
            counts, indices = _tube_topology(_SEGMENTS)
            mesh = UsdGeom.Mesh.Define(stage, path)
            mesh.CreatePointsAttr([Gf.Vec3f(*point) for point in points])
            mesh.CreateFaceVertexCountsAttr(counts)
            mesh.CreateFaceVertexIndicesAttr(indices)
        else:
            points = _annulus_points(
                float(surface["inner_radius_m"]), float(surface["outer_radius_m"]), _SEGMENTS
            )
            counts, indices = _annulus_topology(_SEGMENTS)
            mesh = UsdGeom.Mesh.Define(stage, path)
            mesh.CreatePointsAttr([Gf.Vec3f(*point) for point in points])
            mesh.CreateFaceVertexCountsAttr(counts)
            mesh.CreateFaceVertexIndicesAttr(indices)
            UsdGeom.XformCommonAPI(mesh.GetPrim()).SetTranslate((0.0, 0.0, float(surface["z_m"])))
        low, high = _extent(points)
        mesh.CreateExtentAttr([Gf.Vec3f(*low), Gf.Vec3f(*high)])
        mesh.CreateDoubleSidedAttr(True)
        mesh.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        opacity_attr = mesh.CreateDisplayOpacityAttr([opacity])
        opacity_attr.SetMetadata("interpolation", UsdGeom.Tokens.constant)
        surface_id = mesh.GetPrim().CreateAttribute(
            "primvars:heplabSurfaceId", Sdf.ValueTypeNames.String
        )
        surface_id.Set(str(surface.get("id", "")))

    UsdGeom.Xform.Define(stage, "/World/tracks")
    for index, track in enumerate(tracks):
        points = [(float(p[0]), float(p[1]), float(p[2])) for p in track["points"]]
        charge = track.get("charge", 0)
        color = _CHARGE_COLORS.get(charge, _NEUTRAL_COLOR)
        curves = UsdGeom.BasisCurves.Define(stage, f"/World/tracks/track_{index:03d}")
        curves.CreateTypeAttr(UsdGeom.Tokens.linear)
        curves.CreateCurveVertexCountsAttr([len(points)])
        curves.CreatePointsAttr([Gf.Vec3f(*point) for point in points])
        low, high = _extent(points)
        curves.CreateExtentAttr([Gf.Vec3f(*low), Gf.Vec3f(*high)])
        widths = curves.CreateWidthsAttr([_TRACK_WIDTH_M])
        widths.SetMetadata("interpolation", UsdGeom.Tokens.constant)
        display_color = curves.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        display_color.SetMetadata("interpolation", UsdGeom.Tokens.constant)
        object_id = curves.GetPrim().CreateAttribute(
            "primvars:heplabObjectId", Sdf.ValueTypeNames.Int
        )
        object_id.Set(int(track.get("object_id", index)))
        for crossing in (track.get("trajectory") or {}).get("crossings") or []:
            position = crossing.get("position_m") if isinstance(crossing, dict) else None
            if (
                isinstance(position, list | tuple)
                and len(position) == 3
                and all(isinstance(v, int | float) and math.isfinite(v) for v in position)
            ):
                crossings.append(
                    ([float(v) for v in position], str(crossing.get("surface_id", "")))
                )

    if crossings:
        markers = UsdGeom.Points.Define(stage, "/World/crossings")
        positions = [Gf.Vec3f(*position) for position, _ in crossings]
        markers.CreatePointsAttr(positions)
        low, high = _extent([tuple(position) for position, _ in crossings])
        markers.CreateExtentAttr([Gf.Vec3f(*low), Gf.Vec3f(*high)])
        widths = markers.CreateWidthsAttr([_CROSSING_WIDTH_M])
        widths.SetMetadata("interpolation", UsdGeom.Tokens.constant)
        markers.CreateDisplayColorAttr([Gf.Vec3f(0.95, 0.80, 0.30)])
        surface_ids = markers.GetPrim().CreateAttribute(
            "primvars:heplabSurfaceId", Sdf.ValueTypeNames.StringArray, True
        )
        surface_ids.Set([surface_id for _, surface_id in crossings])
        surface_ids.SetMetadata("interpolation", UsdGeom.Tokens.vertex)

    for name, position in _CAMERAS:
        camera = UsdGeom.Camera.Define(stage, f"/World/{name}")
        transform = UsdGeom.Xformable(camera.GetPrim()).AddTransformOp()
        transform.Set(Gf.Matrix4d(*_look_at_matrix(position, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))))
        camera.CreateFocalLengthAttr(35.0)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 200.0))

    status = stage.GetEditTarget().GetLayer().Save()
    if not status:
        raise ValueError(f"OpenUSD failed to save {output}")
    stage = None  # release the stage before reopening for verification

    reopened = Usd.Stage.Open(str(output))
    if reopened is None:
        raise ValueError(f"exported stage {output} failed to reopen")
    prim_count = sum(1 for _ in reopened.Traverse())
    track_prims = sum(1 for prim in reopened.Traverse() if prim.IsA(UsdGeom.BasisCurves))
    detector_prims = sum(
        1
        for prim in reopened.Traverse()
        if prim.GetParent().GetPath() == Sdf.Path("/World/detector")
    )
    if track_prims != len(tracks) or detector_prims != len(
        [s for s in geometry["surfaces"] if s.get("kind") in {"cylinder", "disk"}]
    ):
        raise ValueError("exported stage does not round-trip its tracks/surfaces")
    summary = {
        "output": str(output),
        "format": "heplab-usd-display-v1",
        "up_axis": "z",
        "meters_per_unit": 1.0,
        "tracks": track_prims,
        "surfaces": detector_prims,
        "crossings": len(crossings),
        "prims": prim_count,
        "bytes": output.stat().st_size,
        "geometry_sha256": geometry.get("sha256", config_hash(geometry)),
    }
    return summary
