"""Download the pinned public CMS image in resumable, hash-verified ranges.

Creates an OCI archive for `docker load`; no daemon settings are changed.
Only public read-scoped registry tokens are used, and tokens are never saved.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import tarfile
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = "cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700"
DIGEST = "sha256:56ef1955c399912f4cdf53e91b39d66aca04a084d8a3a1002a7e27500ac1efa0"
REGISTRY = "https://registry-1.docker.io/v2/" + REPO
CHUNK = 64 * 1024 * 1024
FOLDER = ROOT / ".cache/cmssw-oci"
LOCK = threading.Lock()
TOKEN = ""
TOKEN_TIME = 0.0


def authorization():
    global TOKEN, TOKEN_TIME
    with LOCK:
        if time.monotonic() - TOKEN_TIME > 180 or not TOKEN:
            response = requests.get(
                "https://auth.docker.io/token",
                params={"service": "registry.docker.io", "scope": "repository:" + REPO + ":pull"},
                timeout=60,
            )
            response.raise_for_status()
            TOKEN = response.json()["token"]
            TOKEN_TIME = time.monotonic()
        return {"Authorization": "Bearer " + TOKEN, "Accept-Encoding": "identity"}


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def download_chunk(job):
    digest, size, index = job
    start, stop = index * CHUNK, min((index + 1) * CHUNK, size) - 1
    directory = FOLDER / "chunks" / digest
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{index:04d}"
    if target.exists() and target.stat().st_size == stop - start + 1:
        return stop - start + 1
    for attempt in range(6):
        try:
            headers = {**authorization(), "Range": f"bytes={start}-{stop}"}
            with requests.get(
                REGISTRY + "/blobs/sha256:" + digest, headers=headers, timeout=(30, 90), stream=True
            ) as response:
                response.raise_for_status()
                if (
                    response.status_code != 206
                    or response.headers.get("Content-Range") != f"bytes {start}-{stop}/{size}"
                ):
                    raise ValueError("registry did not honor the exact requested range")
                temporary = target.with_suffix(".partial")
                with temporary.open("wb") as stream:
                    for data in response.iter_content(1024 * 1024):
                        stream.write(data)
                if temporary.stat().st_size != stop - start + 1:
                    raise ValueError("incomplete registry range")
                temporary.replace(target)
            return stop - start + 1
        except (requests.RequestException, ValueError):
            if attempt == 5:
                raise
            time.sleep(min(2**attempt, 30))


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        REGISTRY + "/manifests/" + DIGEST,
        headers={
            **authorization(),
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
        timeout=60,
    )
    response.raise_for_status()
    raw = response.content
    if "sha256:" + hashlib.sha256(raw).hexdigest() != DIGEST:
        raise ValueError("pinned image manifest hash mismatch")
    manifest = response.json()
    descriptors = [manifest["config"], *manifest["layers"]]
    blobs = FOLDER / "blobs/sha256"
    blobs.mkdir(parents=True, exist_ok=True)
    jobs = []
    for item in descriptors:
        digest = item["digest"].removeprefix("sha256:")
        if not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("unsupported blob digest")
        path = blobs / digest
        if path.exists() and path.stat().st_size == item["size"] and file_hash(path) == digest:
            continue
        jobs.extend(
            (digest, item["size"], index) for index in range((item["size"] + CHUNK - 1) // CHUNK)
        )
    print(f"Pinned {DIGEST}; {len(jobs)} ranges queued", flush=True)
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(download_chunk, job) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            done += future.result()
            if done % (512 * 1024 * 1024) < CHUNK:
                print(f"Completed {done / 1e9:.2f} GB of requested ranges", flush=True)
    for item in descriptors:
        digest = item["digest"].split(":")[1]
        path = blobs / digest
        if path.exists() and file_hash(path) == digest:
            continue
        temporary = path.with_suffix(".partial")
        with temporary.open("wb") as stream:
            for index in range((item["size"] + CHUNK - 1) // CHUNK):
                with (FOLDER / "chunks" / digest / f"{index:04d}").open("rb") as chunk:
                    for data in iter(lambda: chunk.read(4 * 1024 * 1024), b""):
                        stream.write(data)
        if temporary.stat().st_size != item["size"] or file_hash(temporary) != digest:
            raise ValueError("assembled OCI blob checksum mismatch; preserve chunks for diagnosis")
        temporary.replace(path)
        print("Verified blob " + digest[:12], flush=True)
    (blobs / DIGEST.split(":")[1]).write_bytes(raw)
    (FOLDER / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n', encoding="utf8")
    index = {
        "schemaVersion": 2,
        "manifests": [
            {
                "mediaType": manifest["mediaType"],
                "digest": DIGEST,
                "size": len(raw),
                "annotations": {"org.opencontainers.image.ref.name": REPO + ":latest"},
            }
        ],
    }
    (FOLDER / "index.json").write_text(json.dumps(index), encoding="utf8")
    archive = ROOT / ".cache/cmssw-oci.tar"
    with tarfile.open(archive.with_suffix(".partial"), "w") as output:
        for path in [FOLDER / "oci-layout", FOLDER / "index.json", *sorted(blobs.iterdir())]:
            if path.suffix != ".partial":
                output.add(path, arcname=path.relative_to(FOLDER).as_posix(), recursive=False)
    archive.with_suffix(".partial").replace(archive)
    print("Verified OCI archive ready: " + str(archive), flush=True)


if __name__ == "__main__":
    main()
