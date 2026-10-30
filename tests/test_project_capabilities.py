"""Keep the website and project overview API on the same capability registry."""

import json
from pathlib import Path

from heplab.server.project import overview

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "src/heplab/data/project-capabilities.json"


def test_public_overview_uses_canonical_capability_registry():
    registry = json.loads(REGISTRY.read_text(encoding="utf8"))
    response = overview()

    assert response["capabilities"] == [
        {key: item[key] for key in ("id", "name", "status", "detail", "href")} for item in registry
    ]
    assert len({item["id"] for item in registry}) == len(registry)
    assert all(item["summary"] and item["includes"] for item in registry)
    assert response["desktop_status"].startswith("Windows desktop build smoke-tested")
