"""Fetch the frozen UL2016 DY calibration projection with explicit partial integrity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import uproot

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest_path = ROOT / "manifests/reference/cms-dy-ul2016.json"
    source = json.loads(manifest_path.read_text(encoding="utf8"))
    target = ROOT / "artifacts/cms/measured/dy-ul16-100k.root"
    target.parent.mkdir(parents=True, exist_ok=True)
    with uproot.open(
        source["url"], handler=uproot.source.http.HTTPSource, num_workers=4, timeout=60
    ) as root:
        if root.file.source.num_bytes != source["source_size_bytes"]:
            raise ValueError("DY source size changed")
        arrays = root["Events"].arrays(
            source["branches"], entry_start=source["entry_start"], entry_stop=source["entry_stop"]
        )
        if len(arrays) != source["entry_stop"] - source["entry_start"]:
            raise ValueError("incomplete DY projection")
    temporary = target.with_suffix(".partial")
    with uproot.recreate(temporary) as result:
        result.mktree("Events", {name: arrays[name] for name in source["branches"]})
    temporary.replace(target)
    source.update(
        {
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "derived_file_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "integrity": "range only; full source checksum not verified",
        }
    )
    (target.parent / "dy-source.json").write_text(
        json.dumps(source, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps({"entries": len(arrays), "record": source["record"], "output": str(target)}))


if __name__ == "__main__":
    main()
