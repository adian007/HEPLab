"""Continue the authorized download -> image load -> geometry export workflow.

Run while pull_cmssw_resumable.py is downloading. State and logs survive a
conversation interruption; there is no recurring schedule or external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:56ef1955c399912f4cdf53e91b39d66aca04a084d8a3a1002a7e27500ac1efa0"
STATE = ROOT / "artifacts/cms/export-workflow"


def state(stage, **fields):
    STATE.mkdir(parents=True, exist_ok=True)
    value = {"stage": stage, "registry_manifest": DIGEST, **fields}
    temporary = STATE / "status.partial"
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")
    temporary.replace(STATE / "status.json")
    print(json.dumps(value), flush=True)


def verify_archive(path):
    with tarfile.open(path, "r") as archive:
        descriptor = "blobs/sha256/" + DIGEST.split(":")[1]
        stream = archive.extractfile(descriptor)
        if stream is None:
            raise ValueError("archive missing pinned manifest")
        raw = stream.read()
        if "sha256:" + hashlib.sha256(raw).hexdigest() != DIGEST:
            raise ValueError("archive manifest mismatch")
        manifest = json.loads(raw)
        for item in [manifest["config"], *manifest["layers"]]:
            stream = archive.extractfile("blobs/sha256/" + item["digest"].split(":")[1])
            if stream is None:
                raise ValueError("archive blob missing")
            hashed, size = hashlib.sha256(), 0
            for data in iter(lambda stream=stream: stream.read(4 * 1024 * 1024), b""):
                hashed.update(data)
                size += len(data)
            if "sha256:" + hashed.hexdigest() != item["digest"] or size != item["size"]:
                raise ValueError("archive blob integrity failure")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cms/geometry/export-2016")
    args = parser.parse_args()
    archive = ROOT / ".cache/cmssw-oci.tar"
    state("waiting_for_resumable_download", archive=str(archive))
    start = time.monotonic()
    try:
        while not archive.exists():
            if time.monotonic() - start > 8 * 3600:
                raise TimeoutError("download did not complete within eight hours")
            time.sleep(10)
        state("verifying_archive")
        verify_archive(archive)
        storage = args.storage_root
        if storage is None:
            storage = (
                Path(os.environ["LOCALAPPDATA"]) / "Docker/wsl"
                if os.name == "nt"
                else Path("/var/lib/docker")
            )
        storage = storage.resolve()
        if not storage.is_dir():
            raise ValueError("Docker storage preflight path does not exist")
        free = shutil.disk_usage(storage).free
        if free < 80 * 1024**3:
            raise ValueError(
                "Docker storage needs 80 GiB free for conservative CMS load/setup budget"
            )
        (STATE / "storage-preflight.json").write_text(
            json.dumps(
                {"path": str(storage), "free_bytes": free, "minimum_free_bytes": 80 * 1024**3},
                indent=2,
            )
            + "\n",
            encoding="utf8",
        )
        state("loading_docker_image")
        image_present = subprocess.run(
            ["docker", "image", "inspect", DIGEST],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=120,
        ).returncode == 0
        if not image_present:
            with (STATE / "docker-load.log").open("w", encoding="utf8") as log:
                subprocess.run(
                    ["docker", "load", "--platform", "linux/amd64", "--input", str(archive)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=3600,
                )
        state("exporting_and_auditing_geometry")
        with (STATE / "export-driver.log").open("w", encoding="utf8") as log:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/run_cms_export.py"),
                    "--output",
                    str(args.output),
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=3700,
            )
        state(
            "export_and_reference_navigation_completed",
            output=str(args.output.resolve()),
            remaining=(
                "Full transport, overlap audit, conditions and measured calibration gates remain"
            ),
        )
    except Exception as exc:
        state("failed", error=str(exc), logs=str(STATE))
        raise


if __name__ == "__main__":
    main()
