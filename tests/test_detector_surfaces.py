"""Surface identity, safe planar module fills and display-only asset routing."""

import importlib.util
from pathlib import Path

import pytest

from heplab.physics.cms_sources import display_asset, display_manifest


def test_surface_assets_are_registered_and_verified():
    manifest = display_manifest()
    for layer in manifest["layers"]:
        for key, suffix, divisor in [
            ("surfaces", "-surfaces", 3),
            ("surface_outlines", "-surface-outlines", 2),
        ]:
            asset = layer[key]
            assert asset["vertices"] % divisor == 0
            assert display_asset(layer["id"] + suffix).stat().st_size == asset["bytes"]
    assert manifest["transport_compatible"] is False
    assert "No material thickness" in manifest["surface_scope"]
    assert manifest["layers"][0]["surfaces"]["planar_outline_triangles"] == 2880
    with pytest.raises(ValueError):
        display_asset("../../pixel-surfaces")


def test_planar_converter_rejects_open_and_nonplanar_polygons(monkeypatch):
    np = pytest.importorskip("numpy")
    import sys

    tools = Path(__file__).resolve().parents[1] / "tools"
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location(
        "surface_converter", tools / "build_cms_surfaces.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    square = np.array(
        [[0, 0, 0], [1, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 0], [0, 1, 0], [0, 1, 0], [0, 0, 0]],
        dtype=float,
    )
    faces, skipped, remainder = module.planar_faces(square)
    assert len(faces) == 6 and skipped == 0 and len(remainder) == 0
    assert len(module.planar_faces(square[:-2])[0]) == 0
    bent = square.copy()
    bent[3:5, 2] = 0.1
    faces, skipped, remainder = module.planar_faces(bent)
    assert len(faces) == 0 and skipped == 1 and len(remainder) == 8
