"""Build display faces from pinned local CMS GLBs; never download or alter outlines.

Native triangles are preferred. Closed, convex, planar outline loops can be
triangulated to show thin module faces; open/nonplanar outlines remain unfilled.
These visual faces carry no material, thickness, alignment or transport claim.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
from import_cms_display import CACHE, OUTPUT, outlines


def planar_faces(lines: np.ndarray) -> tuple[np.ndarray, int, np.ndarray]:
    faces, loop = [], []
    skipped = 0
    used = np.zeros(len(lines) // 2, dtype=bool)
    start = 0
    for edge_index, (a, b) in enumerate(lines.reshape(-1, 2, 3)):
        if loop and not np.array_equal(a, loop[-1]):
            skipped += 1
            loop = []
        if not loop:
            loop = [a]
            start = edge_index
        loop.append(b)
        if len(loop) < 4 or not np.array_equal(b, loop[0]):
            continue
        polygon = np.asarray(loop[:-1], dtype=float)
        loop = []
        if len(polygon) < 3:
            skipped += 1
            continue
        normal = np.cross(polygon[1] - polygon[0], polygon[2] - polygon[0])
        norm = np.linalg.norm(normal)
        span = np.linalg.norm(np.ptp(polygon, axis=0))
        if norm < 1e-12:
            skipped += 1
            continue
        normal /= norm
        # Stored source coordinates are rounded; allow at most a few micrometres.
        planar = np.max(np.abs((polygon - polygon[0]) @ normal)) <= max(2e-6, span * 1e-5)
        edges = np.roll(polygon, -1, axis=0) - polygon
        turns = np.cross(edges, np.roll(edges, -1, axis=0)) @ normal
        convex = np.all(turns >= -1e-12) or np.all(turns <= 1e-12)
        if not planar or not convex:
            skipped += 1
            continue
        for i in range(1, len(polygon) - 1):
            faces.extend([polygon[0], polygon[i], polygon[i + 1]])
        used[start : edge_index + 1] = True
    if loop:
        skipped += 1
    remainder = lines.reshape(-1, 2, 3)[~used].reshape(-1, 3)
    return np.asarray(faces, dtype="<f4").reshape(-1, 3), skipped, remainder


def main() -> None:
    path = OUTPUT / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for layer in manifest["layers"]:
        pieces, remainders, native, derived, skipped = [], [], 0, 0, 0
        for source in layer["sources"]:
            local = CACHE / "geometry/gltf" / source["url"].rsplit("/", 1)[1]
            raw = local.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source["sha256"]:
                raise ValueError(f"source identity mismatch: {local}")
            triangles = outlines(raw, mode=4)
            if len(triangles):
                native += len(triangles) // 3
            else:
                triangles, rejected, remainder = planar_faces(outlines(raw))
                remainders.append(remainder)
                derived += len(triangles) // 3
                skipped += rejected
            pieces.append(triangles)
        values = np.concatenate(pieces).astype("<f4")
        raw = values.tobytes()
        filename = layer["id"] + "-surfaces.f32"
        (OUTPUT / filename).write_bytes(raw)
        layer["surfaces"] = dict(
            file=filename,
            vertices=len(values),
            bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            native_triangles=native,
            planar_outline_triangles=derived,
            unfilled_loops=skipped,
            scope="Display faces only; source triangles or closed convex planar module outlines",
        )
        remainder = np.concatenate(remainders) if remainders else np.empty((0, 3), dtype="<f4")
        remainder_raw = remainder.astype("<f4").tobytes()
        remainder_file = layer["id"] + "-surface-outlines.f32"
        (OUTPUT / remainder_file).write_bytes(remainder_raw)
        layer["surface_outlines"] = dict(
            file=remainder_file,
            vertices=len(remainder),
            bytes=len(remainder_raw),
            sha256=hashlib.sha256(remainder_raw).hexdigest(),
            scope="Source outlines that could not be safely filled; retained in solid mode",
        )
        print(layer["id"], layer["surfaces"])
    manifest["surface_scope"] = (
        "Display-only surfaces; native GLB triangles and triangulated planar module outlines. "
        "No material thickness or transport geometry is inferred."
    )
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
