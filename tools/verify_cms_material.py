"""Independent analytic foil checks for the PyROOT material navigator.

Run with a Python runtime that includes ROOT (the CMS image or scientific runtime).
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]


def main():
    import ROOT

    spec = importlib.util.spec_from_file_location(
        "geometry_worker", ROOT_PATH / "deploy/cms/geometry_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ROOT.gROOT.SetBatch(True)
    geometry = ROOT.TGeoManager("test_material_reference", "analytic two foil reference")
    vacuum = ROOT.TGeoMaterial("vacuum", 0, 0, 0)
    silicon = ROOT.TGeoMaterial("silicon", 28.0855, 14, 2.329)
    air = ROOT.TGeoMedium("vacuum_medium", 1, vacuum)
    sensor = ROOT.TGeoMedium("sensor_medium", 2, silicon)
    top = geometry.MakeBox("world", air, 100, 100, 100)
    geometry.SetTopVolume(top)
    foil = geometry.MakeBox("silicon_1mm", sensor, 0.05, 80, 80)
    thin = geometry.MakeBox("silicon_10um", sensor, 0.0005, 80, 80)
    placements = [ROOT.TGeoTranslation(50, 0, 0), ROOT.TGeoTranslation(60, 0, 0)]
    for obj in [geometry, vacuum, silicon, air, sensor, top, foil, thin, *placements]:
        ROOT.SetOwnership(obj, False)
    top.AddNode(foil, 1, placements[0])
    top.AddNode(thin, 1, placements[1])
    geometry.CloseGeometry()
    report = module.audit(geometry)
    assert report["unique_volumes"] == 3
    assert report["placed_nodes_including_top"] == 3
    assert report["maximum_depth"] == 2
    cases = [
        ([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]),
        ([0.9, 0.0, 0.0], [-1.0, 0.0, 0.0]),
        ([0.0, 0.0, 0.0], [1.0, 0.25, 0.0]),
    ]
    residuals = []
    for origin, direction in cases:
        traced = module.trace_ray(geometry, origin, direction, 0.9)
        material_path = sum(
            row["length_m"] for row in traced["segments"] if row["material_id"] == "silicon"
        )
        ux = abs(direction[0]) / math.hypot(*direction)
        expected = 0.00101 / ux
        residual = abs(material_path - expected)
        assert residual < 1e-9, (material_path, expected)
        assert abs(traced["path_m"] - 0.9) < 1e-9
        assert traced["path_accounting_residual_m"] < 1e-12
        assert abs(traced["x_over_x0"] - expected / (silicon.GetRadLen() / 100)) < 1e-9
        residuals.append(residual)
    try:
        module.trace_ray(geometry, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0.9)
    except ValueError:
        pass
    else:
        raise AssertionError("zero direction accepted")
    result = {
        "status": "passed",
        "root_version": ROOT.gROOT.GetVersion(),
        "analytic_rays": len(cases),
        "thin_foil_m": 1e-5,
        "maximum_material_path_residual_m": max(residuals),
        "scope": "analytic geometry navigation; full CMS geometry not implied",
    }
    target = ROOT_PATH / "artifacts/cms/geometry/analytic-navigation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
