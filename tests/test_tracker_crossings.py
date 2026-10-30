"""CMS tracker crossing search: surface model built once per trajectory."""

from __future__ import annotations

import math

from heplab.physics import detector
from heplab.physics.reference import FourVector, TrackState


def _muon(p=45.0, direction=(0.6, 0.0, 0.8), charge=-1):
    return TrackState(
        (0.0, 0.0, 0.0),
        FourVector(math.hypot(p, 0.10565839), *(p * x for x in direction)),
        charge,
        0.0,
    )


def test_tracker_trajectory_builds_geometry_once_per_call(monkeypatch):
    calls = []
    original = detector.geometry

    def counting(field_model="ideal_bore"):
        calls.append(field_model)
        return original(field_model)

    monkeypatch.setattr(detector, "geometry", counting)
    traced = detector.tracker_trajectory(_muon(), 4.0)
    # One surface model for the crossing search, one for the recorded hash.
    assert calls == ["ideal_bore", "cms_tracker"]
    assert len(traced["points"]) > 100


def test_tracker_crossings_are_ordered_on_known_surfaces():
    traced = detector.tracker_trajectory(_muon(), 4.0)
    ids = {surface["id"] for surface in detector.geometry()["surfaces"]}
    paths = [crossing["path_m"] for crossing in traced["crossings"]]
    assert traced["crossings"]
    assert paths == sorted(paths)
    assert all(crossing["surface_id"] in ids for crossing in traced["crossings"])
