"""Fetch a bounded branch/entry range; never claim whole-source verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import uproot
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest_path = ROOT / "manifests/datasets/run2016g_doublemuon.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf8"))
    source = manifest["files"][0]
    branches = [
        "run",
        "luminosityBlock",
        "event",
        "Muon_pt",
        "Muon_eta",
        "Muon_phi",
        "Muon_mass",
        "Muon_charge",
        "Muon_tightId",
        "Muon_pfRelIso04_all",
        "HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ",
        "HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ",
    ]
    output = ROOT / "artifacts/cms/measured"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "run2016g-100k.root"
    # CERN supports byte ranges; use uproot's HTTP reader rather than fsspec's
    # multipart path, which fails against this endpoint.
    with uproot.open(
        source["url"], handler=uproot.source.http.HTTPSource, num_workers=4, timeout=60
    ) as root:
        if root.file.source.num_bytes != source["size_bytes"]:
            raise ValueError("source size changed")
        arrays = root["Events"].arrays(branches, entry_start=0, entry_stop=100_000)
        if len(arrays) != 100_000:
            raise ValueError("incomplete requested entry range")
        temporary = target.with_suffix(".partial")
        with uproot.recreate(temporary) as result:
            result.mktree("Events", {name: arrays[name] for name in branches})
        temporary.replace(target)
    provenance = {
        "url": source["url"],
        "entry_start": 0,
        "entry_stop": len(arrays),
        "branches": branches,
        "source_size_bytes": source["size_bytes"],
        "declared_adler32": source["adler32"],
        "record": 30522,
        "integrity": "range only; full source checksum not verified",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "derived_file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    (output / "source.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"entries": len(arrays), "output": str(target)}))


if __name__ == "__main__":
    main()
