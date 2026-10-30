"""Build display-only sidecar projections next to the bundled CMS NanoAOD samples.

The existing muon projections stay byte-identical: their SHA-256 is pinned by the
reference calibrations and by every saved analysis. A sidecar holds the same entry
range of the same source file with the reconstructed objects the event display
draws (jets, electrons, photons, taus, isolated tracks, MET, primary vertex and
muon quality), plus run/lumi/event so each entry is joined by identity, not index.

Run from the repository root: python tools/build_cms_display_projection.py [data|mc ...]
Range reads over HTTPS fetch only the baskets needed (~15 MB per sample).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "artifacts/cms/measured"
SAMPLES = {
    "data": ("run2016g-100k.root", "source.json", "run2016g-100k-display.root"),
    "mc": ("dy-ul16-100k.root", "dy-source.json", "dy-ul16-100k-display.root"),
}
IDENTITY = ["run", "luminosityBlock", "event"]
# Collection name -> fields read as <Collection>_<field>; NanoAOD counters follow.
COLLECTIONS = {
    "Jet": ["pt", "eta", "phi", "mass", "jetId", "puId", "btagDeepFlavB",
            "chEmEF", "neEmEF", "chHEF", "neHEF"],
    "Electron": ["pt", "eta", "phi", "mass", "charge", "cutBased", "pfRelIso03_all", "dxy", "dz"],
    "Photon": ["pt", "eta", "phi", "cutBased", "pfRelIso03_all"],
    "Tau": ["pt", "eta", "phi", "charge", "decayMode"],
    "IsoTrack": ["pt", "eta", "phi", "dz"],
    "Muon": ["dxy", "dz", "isGlobal", "isTracker", "isStandalone", "nStations",
             "nTrackerLayers", "ptErr"],
}  # fmt: skip
SCALARS = ["MET_pt", "MET_phi", "MET_sumEt", "PuppiMET_pt", "PuppiMET_phi",
           "PV_x", "PV_y", "PV_z", "PV_npvs", "PV_npvsGood"]  # fmt: skip


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build(role: str) -> dict:
    base_name, record_name, output_name = SAMPLES[role]
    record = json.loads((FOLDER / record_name).read_text(encoding="utf-8"))
    base = FOLDER / base_name
    if sha256(base) != record["derived_file_sha256"]:
        raise SystemExit(f"{base_name} does not match its recorded SHA-256")
    start, stop = record["entry_start"], record["entry_stop"]
    branches = (
        IDENTITY + [f"{c}_{f}" for c, fields in COLLECTIONS.items() for f in fields] + SCALARS
    )
    with uproot.open(record["url"], timeout=120) as source:
        tree = source["Events"]
        missing = sorted(set(branches) - set(tree.keys()))
        if missing:
            raise SystemExit(f"source lacks branches: {', '.join(missing)}")
        arrays = tree.arrays(branches, entry_start=start, entry_stop=stop, library="ak")
    with uproot.open(base) as local:
        reference = local["Events"].arrays(IDENTITY, library="np")
    for name in IDENTITY:
        if not np.array_equal(ak.to_numpy(arrays[name]), reference[name]):
            raise SystemExit(f"{name} differs from {base_name}; refusing to write a sidecar")

    columns: dict = {name: ak.to_numpy(arrays[name]) for name in IDENTITY + SCALARS}
    for collection, fields in COLLECTIONS.items():
        columns[collection] = ak.zip({f: arrays[f"{collection}_{f}"] for f in fields})
    output = FOLDER / output_name
    partial = output.with_suffix(".root.partial")
    with uproot.recreate(partial) as sink:
        # Explicit names keep the NanoAOD layout (nJet, Jet_pt) instead of split records.
        sink.mktree(
            "Events",
            {name: value.type for name, value in ((k, ak.Array(v)) for k, v in columns.items())},
            counter_name=lambda counted: "n" + counted,
            field_name=lambda outer, inner: inner if outer == "" else f"{outer}_{inner}",
        ).extend(columns)
    partial.replace(output)

    with uproot.open(output) as written:
        events = written["Events"]
        if events.num_entries != stop - start:
            raise SystemExit("written sidecar has the wrong entry count")
        written_ids = events.arrays(IDENTITY, library="np")
        if any(not np.array_equal(written_ids[n], reference[n]) for n in IDENTITY):
            raise SystemExit("written sidecar identities do not round-trip")
    description = {
        "record": record["record"],
        "url": record["url"],
        "entry_start": start,
        "entry_stop": stop,
        "joins": base_name,
        "joins_sha256": record["derived_file_sha256"],
        "join_keys": IDENTITY,
        "branches": branches,
        "source_size_bytes": record["source_size_bytes"],
        "integrity": "range only; full source checksum not verified; identities match base file",
        "derived_file_sha256": sha256(output),
        "derived_file_bytes": output.stat().st_size,
        "purpose": "event display only; not read by analyses or calibrations",
        "license": "CC0-1.0",
    }
    (FOLDER / output_name.replace(".root", ".json")).write_text(
        json.dumps(description, indent=2) + "\n", encoding="utf-8"
    )
    return {"role": role, "file": output_name, "bytes": description["derived_file_bytes"],
            "entries": stop - start, "sha256": description["derived_file_sha256"]}  # fmt: skip


def main(argv: list[str]) -> int:
    roles = argv or list(SAMPLES)
    for role in roles:
        if role not in SAMPLES:
            raise SystemExit(f"unknown sample {role!r}; choose from {', '.join(SAMPLES)}")
        print(json.dumps(build(role)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
