"""Validate and optionally execute the HEPLab notebook training gallery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "notebooks" / "gallery"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    manifest = json.loads((GALLERY / "gallery.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "heplab-notebook-gallery-v1":
        raise SystemExit("unsupported notebook gallery schema")

    try:
        import nbformat
    except ImportError as exc:
        raise SystemExit("install nbformat to validate the training gallery") from exc

    if args.execute:
        try:
            import nbclient
        except ImportError as exc:
            raise SystemExit("install nbclient and ipykernel to execute the gallery") from exc

    for entry in manifest["entries"]:
        if not entry.get("runnable"):
            continue
        path = GALLERY / entry["path"]
        notebook = nbformat.read(path, as_version=4)
        nbformat.validator.validate(notebook)
        if args.execute:
            nbclient.NotebookClient(
                notebook,
                timeout=120,
                kernel_name="python3",
            ).execute(cwd=str(GALLERY))
        print(f"PASS {entry['path']}: {entry['scope']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
