"""Fetch pinned CMS iSpy outlines; preserve transforms and attribution.

This exports display edges, never transport solids or material properties.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import struct
import urllib.request
from pathlib import Path

import numpy as np

COMMIT = "42b7d687344877f25213ec7650fc58148e87af2e"
BASE = f"https://raw.githubusercontent.com/cms-outreach/ispy-webgl/{COMMIT}/"
LAYERS = {
    "pixel": ["PixelBarrel3D_V1", "PixelEndcapMinus3D_V1", "PixelEndcapPlus3D_V1"],
    "strips": [
        "SiStripTIB3D_V1",
        "SiStripTIDMinus3D_V1",
        "SiStripTIDPlus3D_V1",
        "SiStripTOB3D_V1",
        "SiStripTECMinus3D_V1",
        "SiStripTECPlus3D_V1",
    ],
    "ecal": ["EcalBarrel3D_V2", "EcalEndcapMinus3D_V1", "EcalEndcapPlus3D_V1"],
    "hcal": [
        "HcalBarrel3D_V1",
        "HcalEndcapMinus3D_V1",
        "HcalEndcapPlus3D_V1",
        "HcalForwardMinus3D_V1",
        "HcalForwardPlus3D_V1",
        "HcalOuter3D_V1",
    ],
    "dt": ["DTs3D_V1"],
    "csc": ["CSC3D_V1"],
    "rpc": ["RPCBarrel3D_V1", "RPCMinusEndcap3D_V1", "RPCPlusEndcap3D_V1"],
}
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/cms-display"
OUTPUT = ROOT / "src/heplab/data/cms-display"


def fetch(relative: str) -> Path:
    path = CACHE / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(BASE + relative, timeout=120) as response:
            data = response.read(32 * 1024 * 1024 + 1)
        if len(data) > 32 * 1024 * 1024:
            raise ValueError("source exceeds download budget")
        path.write_bytes(data)
    return path


def outlines(data: bytes) -> np.ndarray:
    magic, version, length = struct.unpack_from("<III", data)
    if (magic, version, length) != (0x46546C67, 2, len(data)):
        raise ValueError("invalid GLB container")
    size, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("missing GLB JSON")
    doc = json.loads(data[20 : 20 + size])
    offset = 20 + size
    binary_size, kind = struct.unpack_from("<II", data, offset)
    if kind != 0x004E4942 or offset + 8 + binary_size != len(data):
        raise ValueError("invalid GLB binary chunk")
    binary = data[offset + 8 :]
    pieces = []

    def visit(index, parent, ancestry):
        if index in ancestry:
            raise ValueError("cyclic scene")
        node = doc["nodes"][index]
        if "matrix" in node:
            local = np.asarray(node["matrix"]).reshape(4, 4, order="F")
        else:
            x, y, z, w = node.get("rotation", [0, 0, 0, 1])
            rotation = np.array(
                [
                    [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                    [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                    [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
                ]
            )
            local = np.eye(4)
            local[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
            local[:3, 3] = node.get("translation", [0, 0, 0])
        world = parent @ local
        if "mesh" in node:
            for primitive in doc["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 1:
                    continue  # retain explicit outlines; do not invent triangle edges
                if "indices" in primitive:
                    raise ValueError("indexed outlines require an explicit converter")
                accessor = doc["accessors"][primitive["attributes"]["POSITION"]]
                if accessor["componentType"] != 5126 or accessor["type"] != "VEC3":
                    raise ValueError("unsupported position encoding")
                view = doc["bufferViews"][accessor["bufferView"]]
                if view.get("buffer", 0) != 0 or "sparse" in accessor:
                    raise ValueError("unsupported buffer")
                count = accessor["count"]
                if not 0 < count <= 2_000_000 or count % 2:
                    raise ValueError("invalid line vertex count")
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                stride = view.get("byteStride", 12)
                end = start + (count - 1) * stride + 12
                if stride < 12 or end > view.get("byteOffset", 0) + view["byteLength"]:
                    raise ValueError("accessor exceeds view")
                positions = np.ndarray(
                    (count, 3), dtype="<f4", buffer=binary, offset=start, strides=(stride, 4)
                )
                transformed = positions @ world[:3, :3].T + world[:3, 3]
                if not np.isfinite(transformed).all() or np.abs(transformed).max() > 30:
                    raise ValueError("invalid CMS metre coordinates")
                pieces.append(transformed)
        for child in node.get("children", []):
            visit(child, world, ancestry | {index})

    for index in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        visit(index, np.eye(4), set())
    if not pieces:
        raise ValueError("source has no explicit outlines")
    return np.concatenate(pieces).astype("<f4")


def main():
    names = [n for group in LAYERS.values() for n in group]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: fetch("geometry/gltf/" + n + ".glb"), names))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "LICENSE.ispy-webgl").write_bytes(fetch("LICENSE").read_bytes())
    layers = []
    for layer, names in LAYERS.items():
        sources, arrays = [], []
        for name in names:
            relative = "geometry/gltf/" + name + ".glb"
            raw = (CACHE / relative).read_bytes()
            arrays.append(outlines(raw))
            sources.append({"url": BASE + relative, "sha256": hashlib.sha256(raw).hexdigest()})
        values = np.concatenate(arrays)
        raw = values.tobytes()
        filename = layer + ".f32"
        (OUTPUT / filename).write_bytes(raw)
        layers.append(
            {
                "id": layer,
                "file": filename,
                "vertices": len(values),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "bounds_m": [values.min(axis=0).tolist(), values.max(axis=0).tolist()],
                "sources": sources,
            }
        )
    manifest = {
        "schema": "heplab-cms-display-v1",
        "commit": COMMIT,
        "source": "https://github.com/cms-outreach/ispy-webgl",
        "license": "MIT",
        "units": "m",
        "encoding": "little-endian float32 XYZ pairs",
        "scope": "Original-pixel display outlines; ECAL barrel reduced representation",
        "conditions": "No GlobalTag, alignment IOV or material properties in source meshes",
        "transport_compatible": False,
        "omissions": [
            "beam pipe and services",
            "magnet/yoke solids",
            "passive materials",
            "alignment and condition-dependent geometry",
        ],
        "layers": layers,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "layers": len(layers),
                "vertices": sum(x["vertices"] for x in layers),
                "bytes": sum(x["bytes"] for x in layers),
            }
        )
    )


if __name__ == "__main__":
    main()
