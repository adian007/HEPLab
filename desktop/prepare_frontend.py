"""Assemble the simulator workbench as the desktop app's frontend.

Run from desktop/ (Tauri's beforeBuildCommand does this): python prepare_frontend.py
The workbench files are copied unchanged from src/heplab/server/static into the
paths index.html already references; the pinned CMS display layers are bundled
so they load locally instead of over IPC. desktop/frontend is generated output.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
ROOT = DESKTOP.parent
STATIC = ROOT / "src/heplab/server/static"
DISPLAY = ROOT / "src/heplab/data/cms-display"
OUT = DESKTOP / "frontend"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "ui").mkdir(parents=True)
    (OUT / "cms-display").mkdir()
    shutil.copy2(STATIC / "index.html", OUT / "index.html")
    for name in (
        "workbench.js",
        "event-display-gl.js",
        "detector-cutaway.js",
        "data-workspace.js",
        "workbench.css",
        "heplab-detector.png",
    ):
        shutil.copy2(STATIC / name, OUT / "ui" / name)
    for name in ("intro.min.js", "introjs.min.css"):
        shutil.copy2(STATIC / "vendor" / "introjs" / name, OUT / "ui" / name)
    manifest = json.loads((DISPLAY / "manifest.json").read_text(encoding="utf-8"))
    for layer in manifest["layers"]:
        for asset in [layer, *[layer[k] for k in ("surfaces", "surface_outlines") if k in layer]]:
            data = (DISPLAY / asset["file"]).read_bytes()
            if len(data) != asset["bytes"] or hashlib.sha256(data).hexdigest() != asset["sha256"]:
                raise SystemExit(f"display layer {asset['file']} failed integrity check")
            (OUT / "cms-display" / asset["file"]).write_bytes(data)
    shutil.copy2(DISPLAY / "LICENSE.ispy-webgl", OUT / "cms-display" / "LICENSE.ispy-webgl")
    files = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    print(json.dumps({"frontend": str(OUT.relative_to(ROOT)), "files": len(files)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
