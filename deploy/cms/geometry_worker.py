"""CMSSW/PyROOT geometry audit and straight-ray material reference.

Compatible with the Python 2 runtime in the official CMSSW image. This is
material navigation, not energy-loss, scattering or shower simulation.
"""
from __future__ import print_function  # noqa: UP010

import argparse
import collections
import hashlib
import json
import math
import os

MASS_FRACTION_SUM_TOLERANCE = 1e-4


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            data = stream.read(1024 * 1024)
            if not data:
                break
            value.update(data)
    return value.hexdigest()


def finite(value):
    return not (math.isnan(value) or math.isinf(value))


def material_record(material):
    density = float(material.GetDensity())
    if not finite(density) or density < 0:
        raise ValueError("invalid material density")
    record = {"id": str(material.GetName()), "density_g_cm3": density,
              "radiation_length_m": None, "interaction_length_m": None}
    if density > 0:
        lengths = [float(material.GetRadLen()) / 100, float(material.GetIntLen()) / 100]
        if not all(finite(v) and v > 0 for v in lengths):
            raise ValueError("invalid radiation/interaction length: " + record["id"])
        record["radiation_length_m"], record["interaction_length_m"] = lengths
    elements = []
    if material.IsMixture():
        for index in range(material.GetNelements()):
            elements.append({"atomic_mass": float(material.GetAmixt()[index]),
                             "atomic_number": float(material.GetZmixt()[index]),
                             "mass_fraction": float(material.GetWmixt()[index])})
        if any(not finite(value) or value < 0 for e in elements for value in e.values()):
            raise ValueError("invalid material composition")
        source_fraction_sum = sum(v["mass_fraction"] for v in elements)
        if (
            not finite(source_fraction_sum)
            or source_fraction_sum <= 0
            or abs(source_fraction_sum - 1) > MASS_FRACTION_SUM_TOLERANCE
        ):
            raise ValueError("mixture mass fractions do not sum to one")
        record["source_mass_fraction_sum"] = source_fraction_sum
        for element in elements:
            element["mass_fraction"] /= source_fraction_sum
    else:
        elements = [{"atomic_mass": float(material.GetA()),
                     "atomic_number": float(material.GetZ()), "mass_fraction": 1.0}]
    if any(not finite(value) or value < 0 for e in elements for value in e.values()):
        raise ValueError("invalid material composition")
    record["elements"] = elements
    return record


def audit(manager):
    materials, volumes, shapes = {}, {}, collections.Counter()
    for volume in manager.GetListOfVolumes():
        name = str(volume.GetName())
        if name in volumes:
            raise ValueError("duplicate volume name: " + name)
        if not volume.GetShape() or not volume.GetMaterial():
            raise ValueError("volume missing shape or material: " + name)
        record = material_record(volume.GetMaterial())
        if record["id"] in materials and materials[record["id"]] != record:
            raise ValueError("ambiguous material identity")
        materials[record["id"]] = record
        children = [str(node.GetVolume().GetName()) for node in (volume.GetNodes() or [])]
        shapes[str(volume.GetShape().ClassName())] += 1
        volumes[name] = {"material_id": record["id"], "children": children,
                         "shape": str(volume.GetShape().ClassName())}
    memo = {}

    def count(name, ancestors):
        if name in ancestors:
            raise ValueError("cyclic volume graph")
        if name in memo:
            return memo[name]
        nodes, depth = 1, 1
        for child in volumes[name]["children"]:
            child_nodes, child_depth = count(child, ancestors | set([name]))
            nodes += child_nodes
            depth = max(depth, 1+child_depth)
        if depth >= 100:
            raise ValueError("geometry reaches export depth limit")
        memo[name] = (nodes, depth)
        return nodes, depth

    nodes, depth = count(str(manager.GetTopVolume().GetName()), set())
    return {"unique_volumes": len(volumes), "placed_nodes_including_top": nodes,
            "maximum_depth": depth, "shape_counts": dict(shapes),
            "materials": sorted(materials.values(), key=lambda value: value["id"]),
            "radiation_length_source": "ROOT composition-derived; Geant4 equivalence pending",
            "overlap_validation": "not performed by this audit"}


def trace_ray(manager, origin_m, direction, max_path_m):
    if (len(origin_m) != 3 or len(direction) != 3
            or not all(finite(v) for v in origin_m+direction+[max_path_m])
            or not 0 < max_path_m <= 50):
        raise ValueError("invalid ray domain")
    norm = math.sqrt(sum(v*v for v in direction))
    if norm <= 0:
        raise ValueError("zero ray direction")
    direction = [v/norm for v in direction]
    node = manager.InitTrack(*( [v*100 for v in origin_m]+direction ))
    if not node:
        raise ValueError("ray starts outside geometry")
    segments, path, zeros = [], 0.0, 0
    maximum_coordinate_residual = 0.0
    for _unused in range(100000):
        remaining = max_path_m-path
        if remaining <= 1e-10 or manager.IsOutside():
            break
        node = manager.GetCurrentNode()
        if not node:
            raise ValueError("navigator lost current node")
        material = material_record(node.GetVolume().GetMaterial())
        volume_path = str(manager.GetPath())
        manager.FindNextBoundaryAndStep(remaining*100, False)
        step = float(manager.GetStep()) / 100
        if not finite(step) or step < 0 or step > remaining+1e-8:
            raise ValueError("invalid navigator step")
        if step <= 1e-14:
            zeros += 1
            if zeros > 64:
                raise ValueError("boundary navigation stalled; no epsilon skip permitted")
            continue
        zeros = 0
        point = manager.GetCurrentPoint()
        residual = math.sqrt(sum((point[i]/100-(origin_m[i]+(path+step)*direction[i]))**2
                                 for i in range(3)))
        maximum_coordinate_residual = max(maximum_coordinate_residual, residual)
        if residual > 1e-6:
            raise ValueError("navigator coordinate/path disagreement exceeds 1 micrometre")
        segment = {"path_start_m": path, "length_m": step, "volume_path": volume_path,
                   "material_id": material["id"], "density_g_cm3": material["density_g_cm3"],
                   "radiation_length_m": material["radiation_length_m"],
                   "interaction_length_m": material["interaction_length_m"]}
        segments.append(segment)
        path += step
    else:
        raise ValueError("material navigation step budget exhausted")
    residual = abs(sum(s["length_m"] for s in segments)-path)
    if residual > 1e-9:
        raise ValueError("material path accounting failed")
    return {"origin_m": origin_m, "direction": direction, "segments": segments,
            "path_m": path, "path_accounting_residual_m": residual,
            "max_coordinate_residual_m": maximum_coordinate_residual,
            "termination": "geometry_exit" if manager.IsOutside() else "path_budget",
            "x_over_x0": sum(s["length_m"]/s["radiation_length_m"] for s in segments
                             if s["radiation_length_m"]),
            "x_over_lambda": sum(s["length_m"]/s["interaction_length_m"] for s in segments
                                 if s["interaction_length_m"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geometry")
    parser.add_argument("--log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.log) as stream:
        logs = stream.read()
    if "COULD NOT MAKE" in logs or "Fatal Exception" in logs:
        raise ValueError("CMSSW log reports incomplete or failed solid conversion")
    import ROOT
    ROOT.gROOT.SetBatch(True)
    source = ROOT.TFile.Open(args.geometry)
    if not source or source.IsZombie():
        raise ValueError("geometry file cannot be opened")
    manager = source.Get("cmsGeo")
    if not manager:
        raise ValueError("missing cmsGeo TGeoManager")
    report = audit(manager)
    report.update({"schema": "heplab-tgeo-material-reference-v1",
                   "geometry_sha256": digest(args.geometry), "log_sha256": digest(args.log),
                   "cmssw_version": str(source.Get("CMSSW_VERSION").GetTitle()),
                   "geometry_tag": str(source.Get("tag").GetTitle()),
                   "root_version": str(ROOT.gROOT.GetVersion()),
                   "scope": ("ideal geometry material navigation; "
                             "no aligned conditions or shower model")})
    rays = []
    for eta in [-2.4, -1.8, -1.2, -.6, 0, .6, 1.2, 1.8, 2.4]:
        for index in range(12):
            phi = 2*math.pi*(index+.173)/12
            direction = [math.cos(phi)/math.cosh(eta),
                         math.sin(phi)/math.cosh(eta), math.tanh(eta)]
            rays.append(dict(trace_ray(manager, [0., 0., 0.], direction, 20.), eta=eta, phi=phi))
    report["rays"] = rays
    report["navigation_status"] = "reference_rays_completed"
    temporary = args.output+".partial"
    with open(temporary, "w") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.rename(temporary, args.output)
    print(json.dumps({"volumes": report["unique_volumes"], "materials": len(report["materials"]),
                      "depth": report["maximum_depth"], "rays": len(rays)}))


if __name__ == "__main__":
    main()
