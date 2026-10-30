"""Build the checked-in public gallery from deterministic synthetic examples."""

from __future__ import annotations

import json
import math
import struct
import threading
from pathlib import Path

import heplab
from heplab.analyses.dimuon.run import invariant_mass
from heplab.export.web_page import export_html
from heplab.io.provenance import config_hash
from heplab.labs import practice_events
from heplab.server.workbench import RunConfig, bench

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "web" / "public" / "examples"
CMS_DISPLAY = ROOT / "src" / "heplab" / "data" / "cms-display"


def cms_display_payload() -> dict:
    """Compact, self-contained linework and bounds from pinned CMS display meshes."""
    manifest = json.loads((CMS_DISPLAY / "manifest.json").read_text(encoding="utf-8"))
    layers = []
    for layer in manifest["layers"]:
        min_radius = min_z = math.inf
        max_radius = max_z = -math.inf
        values = struct.iter_unpack("<fff", (CMS_DISPLAY / layer["file"]).read_bytes())
        stride_by_layer = {
            "pixel": 1,
            "strips": 10,
            "ecal": 20,
            "hcal": 15,
            "dt": 1,
            "csc": 1,
            "rpc": 5,
        }
        stride = stride_by_layer[layer["id"]]
        xy_lines, zr_lines = [], []
        start = None
        segment = 0
        for x, y, z in values:
            radius = math.hypot(x, y)
            min_radius, max_radius = min(min_radius, radius), max(max_radius, radius)
            min_z, max_z = min(min_z, z), max(max_z, z)
            if start is None:
                start = (x, y, z)
                continue
            if segment % stride == 0:
                x0, y0, z0 = start
                xy_lines.extend((round(x0, 4), round(y0, 4), round(x, 4), round(y, 4)))
                zr_lines.extend(
                    (round(z0, 4), round(math.hypot(x0, y0), 4), round(z, 4), round(radius, 4))
                )
            segment += 1
            start = None
        layers.append(
            {
                "id": layer["id"],
                "min_radius_m": round(min_radius, 4),
                "max_radius_m": round(max_radius, 4),
                "min_z_m": round(min_z, 4),
                "max_z_m": round(max_z, 4),
                "sha256": layer["sha256"],
                "xy_lines": xy_lines,
                "zr_lines": zr_lines,
            }
        )
    return {
        "source": manifest["source"],
        "commit": manifest["commit"],
        "license": manifest["license"],
        "license_notice": (CMS_DISPLAY / "LICENSE.ispy-webgl").read_text(encoding="utf-8"),
        "scope": (
            "decimated module linework and envelopes from pinned CMS display meshes; "
            "not transport geometry"
        ),
        "layers": layers,
    }


def main() -> None:
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    config = {
        "selection": {
            "muons": {"min_pt": 20, "max_rel_iso": 0.15},
            "pairs": {"require_opposite_charge": True},
        },
        "binning": {"dimuon_mass": {"range": [40, 140], "bins": 100}},
    }
    result = heplab.run(practice_events(3000, seed=7), config=config)
    result["provenance"]["sample_notice"] = "synthetic deterministic teaching sample; not CMS data"
    result["result_sha256"] = config_hash(
        {
            key: value
            for key, value in result.items()
            if key
            not in {
                "dataset",
                "provenance",
                "provenance_digest",
                "created_at",
                "reproduction",
                "result_sha256",
                "payload_content_sha256",
            }
        }
    )
    export_html(
        result,
        EXAMPLES / "synthetic-z-dimuon.html",
        title="Synthetic Z→μμ teaching sample",
    )

    events = practice_events(4000, seed=7)
    lab_result = heplab.run(events, config=config)
    fit = heplab.fit_peak(lab_result)
    first = next(event for event in events if len(event.get("Muon", [])) >= 2)
    demo = {
        "events": len(events),
        "events_with_muon_pair": sum(len(event.get("Muon", [])) >= 2 for event in events),
        "first_event": first["EventInfo"]["event"],
        "muons": first["Muon"][:2],
        "hand_mass_gev": invariant_mass(*first["Muon"][:2]),
        "histogram": lab_result["histogram"],
        "cutflow": lab_result["cutflow"],
        "fit": fit,
        "reference_mass_gev": 91.1876,
        "sample": "heplab-practice-z-mumu-v1",
    }
    data_dir = ROOT / "web" / "src" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "z-boson-demo.json").write_text(
        json.dumps(demo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    event = bench(
        RunConfig(seed=42, field_model="cms_tracker", source_model="angular_sample"),
        threading.Event(),
    )
    event["provenance"] = {
        "kind": "synthetic_workbench_fixture",
        "sample_notice": "synthetic angular back-to-back muon pair; not a collision event",
        "config_sha256": config_hash(event["config"]),
        "seed": event["config"]["seed"],
    }
    event["cms_display_geometry"] = cms_display_payload()
    event["result_sha256"] = config_hash(event)
    export_html(event, EXAMPLES / "declared-muon-event.html", title="Declared muon workbench event")


if __name__ == "__main__":
    main()
