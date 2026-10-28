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
    for name in ("workbench.js", "workbench.css"):
        shutil.copy2(STATIC / name, OUT / "ui" / name)
    manifest = json.loads((DISPLAY / "manifest.json").read_text(encoding="utf-8"))
    for layer in manifest["layers"]:
        data = (DISPLAY / layer["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != layer["sha256"]:
            raise SystemExit(f"display layer {layer['file']} failed integrity check")
        (OUT / "cms-display" / layer["file"]).write_bytes(data)
    shutil.copy2(DISPLAY / "LICENSE.ispy-webgl", OUT / "cms-display" / "LICENSE.ispy-webgl")
    files = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*") if p.is_file())
    print(json.dumps({"frontend": str(OUT.relative_to(ROOT)), "files": len(files)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
