"""Run ROOT TGeo containment and overlap checks on an exported CMS geometry."""

import argparse
import collections
import hashlib
import json
import math
import os


def digest(path):
    value = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            data = stream.read(1024 * 1024)
            if not data:
                break
            value.update(data)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("geometry")
    parser.add_argument("--output", required=True)
    parser.add_argument("--tolerance-cm", type=float, default=0.01)
    args = parser.parse_args()
    if (
        math.isnan(args.tolerance_cm)
        or math.isinf(args.tolerance_cm)
        or not 1e-6 <= args.tolerance_cm <= 1
    ):
        raise ValueError("overlap tolerance must be between 1e-6 and 1 cm")

    import ROOT

    ROOT.gROOT.SetBatch(True)
    source = ROOT.TFile.Open(args.geometry)
    if not source or source.IsZombie():
        raise ValueError("geometry file cannot be opened")
    manager = source.Get("cmsGeo")
    if not manager:
        raise ValueError("missing cmsGeo TGeoManager")

    manager.CheckOverlaps(args.tolerance_cm)
    overlaps = manager.GetListOfOverlaps()
    records = []
    if overlaps:
        for index in range(overlaps.GetEntries()):
            item = overlaps.At(index)
            first = item.GetFirstVolume()
            second = item.GetSecondVolume()
            title = str(item.GetTitle())
            if " extruded by: " in title:
                kind = "extrusion"
            elif " overlapping " in title:
                kind = "overlap"
            else:
                kind = "other"
            records.append({
                "name": str(item.GetName()),
                "title": title,
                "kind": kind,
                "overlap_cm": float(item.GetOverlap()),
                "first_volume": str(first.GetName()) if first else None,
                "second_volume": str(second.GetName()) if second else None,
            })

    summary = collections.defaultdict(list)
    for record in records:
        summary[record["kind"]].append(record["overlap_cm"])
    report = {
        "schema": "heplab-tgeo-overlap-audit-v1",
        "geometry_sha256": digest(args.geometry),
        "root_version": str(ROOT.gROOT.GetVersion()),
        "tolerance_cm": args.tolerance_cm,
        "overlap_count": len(records),
        "classification_counts": dict(
            (kind, len(values)) for kind, values in summary.items()
        ),
        "maximum_overlap_cm_by_kind": dict(
            (kind, max(values)) for kind, values in summary.items()
        ),
        "records": records,
        "interpretation": (
            "TGeo overlap and containment candidates; findings require review and are not "
            "automatically classified as physical errors"
        ),
    }
    temporary = args.output + ".partial"
    with open(temporary, "w") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.rename(temporary, args.output)
    print(json.dumps({
        "root_version": report["root_version"],
        "overlap_count": report["overlap_count"],
        "tolerance_cm": report["tolerance_cm"],
        "output": args.output,
    }))


if __name__ == "__main__":
    main()
