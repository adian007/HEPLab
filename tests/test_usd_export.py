"""OpenUSD export round-trips a real reference trajectory into a vendor-neutral stage."""

import math

import pytest

from heplab.physics.detector import geometry, trajectory
from heplab.physics.reference import FourVector, TrackState

pxr = pytest.importorskip("pxr.Usd", reason="USD export requires `pip install 'heplab[usd]'`")


def _display_payload() -> dict:
    tracks = []
    for index, (charge, direction) in enumerate(((1, (1.0, 0.0, 0.0)), (-1, (-1.0, 0.0, 0.0)))):
        state = TrackState(
            (0.0, 0.0, 0.0),
            FourVector(math.hypot(10.0, 0.10565839), *(charge * 10.0 * v for v in direction)),
            charge,
            0.0,
        )
        traced = trajectory(state, max_path=1.0, step=0.05)
        tracks.append(
            {
                "object_id": index,
                "charge": charge,
                "points": traced["points"],
                "trajectory": traced,
            }
        )
    return {"event": 0, "tracks": tracks, "geometry": geometry()}


def _expected_surfaces(payload: dict) -> int:
    return sum(1 for s in payload["geometry"]["surfaces"] if s.get("kind") in {"cylinder", "disk"})


def test_export_round_trip(tmp_path):
    from pxr import Sdf, Usd, UsdGeom

    from heplab.export.usd import export_event

    payload = _display_payload()
    output = tmp_path / "event.usd"
    summary = export_event(payload, output)
    assert output.is_file() and summary["bytes"] > 0
    assert summary["tracks"] == len(payload["tracks"])
    assert summary["surfaces"] == _expected_surfaces(payload)
    assert summary["crossings"] == sum(
        len(track["trajectory"]["crossings"]) for track in payload["tracks"]
    )

    stage = Usd.Stage.Open(str(output))
    assert stage is not None
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    assert stage.GetDefaultPrim().GetPath() == Sdf.Path("/World")
    assert summary["prims"] == sum(1 for _ in stage.Traverse())

    detector = stage.GetPrimAtPath("/World/detector")
    assert len(detector.GetChildren()) == _expected_surfaces(payload)
    bore = stage.GetPrimAtPath("/World/detector/solenoid_bore")
    assert bore.IsValid()
    assert bore.GetAttribute("primvars:heplabSurfaceId").Get() == "solenoid-bore"

    curve = UsdGeom.BasisCurves(stage.GetPrimAtPath("/World/tracks/track_000"))
    assert curve.GetCurveVertexCountsAttr().Get() == [len(payload["tracks"][0]["points"])]
    exported_points = curve.GetPointsAttr().Get()
    assert len(exported_points) == len(payload["tracks"][0]["points"])
    for written, source in zip(exported_points, payload["tracks"][0]["points"], strict=True):
        assert all(abs(a - b) < 1e-5 for a, b in zip(written, source, strict=True))
    color = curve.GetDisplayColorAttr().Get()[0]
    assert color[0] > 0.8  # positive charge renders red

    crossings = UsdGeom.Points(stage.GetPrimAtPath("/World/crossings"))
    assert len(crossings.GetPointsAttr().Get()) == summary["crossings"]


def test_export_rejects_payloads_without_tracks(tmp_path):
    from heplab.export.usd import export_event

    with pytest.raises(ValueError, match="tracks"):
        export_event({"event": 0}, tmp_path / "empty.usd")
    with pytest.raises(ValueError, match="surfaces"):
        export_event({"tracks": [], "geometry": {}}, tmp_path / "empty.usd")


def test_export_refuses_overwrite(tmp_path):
    from heplab.export.usd import export_event

    payload = _display_payload()
    output = tmp_path / "event.usd"
    export_event(payload, output)
    with pytest.raises(ValueError, match="already exists"):
        export_event(payload, output)
