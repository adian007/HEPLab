"""Archive official field inputs and quantify OAE/ideal-field reference errors."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np

from heplab.physics.cms_field import MODEL, SOURCE, tracker_field

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "3be1b543120a90dcbb8c1584da0ba27ca980a24d"
GRID = "3b2fd38885ce884324f14470624dddd335865d0a"
CMSSW = "c04fa510bb587b8ee3fa171888468f80de714fa8"


def main():
    output = ROOT / "artifacts/cms/field"
    output.mkdir(parents=True, exist_ok=True)
    sources = [
        (
            "cms-data/MagneticField-Engine",
            ENGINE,
            "Regression/referenceField_160812_RII_3_8T.bin",
            "referenceField_160812_RII_3_8T.bin",
        ),
        ("cms-data/MagneticField-Interpolation", GRID, "grid_160812_3_8t/merged.bin", "merged.bin"),
        (
            "cms-data/MagneticField-Interpolation",
            GRID,
            "grid_160812_3_8t/merged.index",
            "merged.index",
        ),
    ]
    sources += [
        ("cms-sw/cmssw", CMSSW, path, Path(path).name)
        for path in [
            "MagneticField/GeomBuilder/data/MagneticFieldVolumes_160812_1.xml",
            "MagneticField/GeomBuilder/data/MagneticFieldVolumes_160812_2.xml",
            "MagneticField/Engine/python/volumeBasedMagneticField_160812_cfi.py",
            "MagneticField/ParametrizedEngine/src/BCyl.h",
            "MagneticField/ParametrizedEngine/src/TkBfield.cc",
        ]
    ]
    inventory = []
    for repo, commit, relative, name in sources:
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{relative}"
        path = output / name
        if not path.exists():
            with urllib.request.urlopen(url, timeout=120) as response:
                raw = response.read(100_000_001)
            if len(raw) > 100_000_000:
                raise ValueError("field source exceeds download budget")
            temporary = path.with_suffix(path.suffix + ".partial")
            temporary.write_bytes(raw)
            temporary.replace(path)
        expected_blobs = {
            "merged.bin": "1d942b61544b5f42a1aa0e6f2309b6eb9ef5da24",
            "merged.index": "aaf16dcc84a438fdb5848f228c174c5f169d75f3",
        }
        if name in expected_blobs:
            content = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content)
            if blob.hexdigest() != expected_blobs[name]:
                raise ValueError("official field grid Git blob identity mismatch")
        inventory.append(
            {
                "url": url,
                "file": name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    expected = "b785fa7a7a16b9dbbbabaf7751bd64e0cb7a15a0e51fcd9c60aa4263bde90e8b"
    if inventory[0]["sha256"] != expected:
        raise ValueError("official regression payload identity mismatch")
    points = np.fromfile(output / inventory[0]["file"], dtype="<f4").reshape(-1, 6).astype(float)
    if len(points) != 1_000_000 or not np.isfinite(points).all():
        raise ValueError("invalid field reference table")
    points[:, :3] /= 100  # CMS GlobalPoint cm -> HEPLab metres; B already in tesla
    tracker = points[(np.hypot(points[:, 0], points[:, 1]) < 1.15) & (abs(points[:, 2]) < 2.8)]
    predicted = np.array([tracker_field(row[:3].tolist()) for row in tracker])
    difference = np.linalg.norm(predicted - tracker[:, 3:], axis=1)
    ideal_difference = np.linalg.norm(tracker[:, 3:] - [0, 0, 3.8], axis=1)
    report = {
        "schema": "heplab-cms-field-reference-v1",
        "model": MODEL,
        "source": SOURCE,
        "reference_rows": len(points),
        "tracker_rows": len(tracker),
        "max_vector_error_t": float(difference.max()),
        "rms_vector_error_t": float(np.sqrt(np.mean(difference**2))),
        "gate_max_vector_error_t": 2e-6,
        "passed": bool(difference.max() <= 2e-6),
        "ideal_3_8t_mean_vector_error_t": float(ideal_difference.mean()),
        "ideal_3_8t_max_vector_error_t": float(ideal_difference.max()),
        "scope": (
            "Implementation regression against CMS software reference; "
            "not new measured-data calibration"
        ),
        "full_map_transport": "not enabled: volume navigation and conditions IOV unresolved",
        "conditions": {
            "target_data": "Run2016G UL NanoAOD record 30522",
            "nano_global_tag": "106X_dataRun2_v35",
            "runs": [278820, 280385],
            "payload_iov_verified": False,
        },
        "inventory": inventory,
    }
    for path in [
        output / "validation.json",
        ROOT / "src/heplab/data/reference/cms-field-validation.json",
    ]:
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({k: report[k] for k in ["tracker_rows", "max_vector_error_t", "passed"]}))
    if not report["passed"]:
        raise SystemExit("field regression gate failed")


if __name__ == "__main__":
    main()
