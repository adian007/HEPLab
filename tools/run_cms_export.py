"""Run and audit the CMS ideal geometry export in a digest-pinned container."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700:latest"
MANIFEST_DIGEST = "sha256:56ef1955c399912f4cdf53e91b39d66aca04a084d8a3a1002a7e27500ac1efa0"
SCRIPT = r"""
set -eu
if ! command -v cmsRun >/dev/null 2>&1; then
  for setup in /opt/cms/cmsset_default.sh /cvmfs/cms.cern.ch/cmsset_default.sh; do
    if [ -f "$setup" ]; then source "$setup"; break; fi
  done
  release="${CMSSW_BASE:-/code/CMSSW_10_6_30}"
  if [ ! -d "$release/src" ]; then
    release=$(find /code /opt/cms /home/cmsusr -maxdepth 4 -type d \
      -name CMSSW_10_6_30 2>/dev/null | head -n 1)
  fi
  test -n "$release"
  cd "$release/src"
  eval "$(scram runtime -sh)"
fi
test "$CMSSW_VERSION" = CMSSW_10_6_30
cd /output
cmsRun /heplab/export_geometry_2016_cfg.py > geometry-export.log 2>&1
python /heplab/geometry_worker.py cms-ideal-2016.root --log geometry-export.log \
  --output material-reference.json > geometry-audit.log 2>&1
"""


def command(args):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf8",
        errors="replace",
        check=True,
        timeout=120,
    ).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/cms/geometry/export-2016")
    args = parser.parse_args()
    target = args.output.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("export directory must be new or empty; preserve prior evidence")
    if args.pull:
        subprocess.run(
            ["docker", "pull", "--platform", "linux/amd64", IMAGE], check=True, timeout=14400
        )
    try:
        identity = json.loads(command(["docker", "image", "inspect", IMAGE]))[0]
    except subprocess.CalledProcessError:
        identity = json.loads(command(["docker", "image", "inspect", MANIFEST_DIGEST]))[0]
    digests = [v for v in identity["RepoDigests"] if v.startswith(IMAGE.split(":")[0] + "@")]
    if identity["Architecture"] != "amd64" or identity["Os"] != "linux":
        raise ValueError("expected Linux amd64 CMSSW image")
    if len(digests) == 1 and digests[0].endswith("@" + MANIFEST_DIGEST):
        pinned = digests[0]
    elif not digests:
        # Docker may identify an OCI-loaded image by manifest digest rather than config digest.
        manifest_path = ROOT / ".cache/cmssw-oci/blobs/sha256" / MANIFEST_DIGEST.split(":")[1]
        raw = manifest_path.read_bytes()
        if "sha256:" + hashlib.sha256(raw).hexdigest() != MANIFEST_DIGEST:
            raise ValueError("local OCI registry manifest identity mismatch")
        if IMAGE not in identity["RepoTags"]:
            raise ValueError("pinned CMS image is not tagged with the expected repository name")
        config_descriptor = json.loads(raw)["config"]
        config_digest = config_descriptor["digest"].split(":")[1]
        config_path = ROOT / ".cache/cmssw-oci/blobs/sha256" / config_digest
        config_raw = config_path.read_bytes()
        if (
            "sha256:" + hashlib.sha256(config_raw).hexdigest() != config_descriptor["digest"]
            or len(config_raw) != config_descriptor["size"]
        ):
            raise ValueError("local OCI image config identity mismatch")
        config = json.loads(config_raw)
        if identity["Id"] == config_descriptor["digest"]:
            pinned = identity["Id"]
        elif (
            identity["Id"] == MANIFEST_DIGEST
            and identity["RootFS"]["Layers"] == config["rootfs"]["diff_ids"]
        ):
            pinned = identity["Id"]
        else:
            raise ValueError("loaded image does not match verified registry config")
    else:
        raise ValueError("CMS image registry digest does not match pinned release")
    target.mkdir(parents=True, exist_ok=True)
    source = ROOT / "deploy/cms"
    inventory = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")}
    record = {
        "schema": "heplab-cmssw-export-run-v1",
        "image": pinned,
        "registry_manifest": MANIFEST_DIGEST,
        "image_id": identity["Id"],
        "config_sha256": inventory,
        "geometry": "ideal Extended2016 DDD, not aligned reconstruction conditions",
        "material_transport_status": "not yet validated",
        "status": "running",
    }
    run_path = target / "run.json"
    run_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    container_name = "heplab-cms-geometry-" + uuid.uuid4().hex[:8]
    argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--platform",
        "linux/amd64",
        "--memory",
        "8g",
        "--cpus",
        "4",
        "--network",
        "none",
        "--mount",
        f"type=bind,source={source},target=/heplab,readonly",
        "--mount",
        f"type=bind,source={target},target=/output",
        pinned,
        "/bin/bash",
        "-c",
        SCRIPT,
    ]
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf8", errors="replace", timeout=3600
        )
        (target / "container.log").write_text(result.stdout + result.stderr, encoding="utf8")
        record["exit_code"] = result.returncode
        if result.returncode:
            raise RuntimeError("CMS export/audit failed; inspect preserved output logs")
        audit_path = target / "material-reference.json"
        audit = json.loads(audit_path.read_text(encoding="utf8"))
        if audit["navigation_status"] != "reference_rays_completed" or len(audit["rays"]) != 108:
            raise ValueError("incomplete material reference audit")
        record["status"] = "exported_and_reference_navigated"
        record["artifacts"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in target.iterdir()
            if p.is_file() and p.name != "run.json"
        }
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "stop", "--time", "10", container_name],
            capture_output=True,
            timeout=30,
            check=False,
        )
        record["status"] = "timed_out"
        raise
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        raise
    finally:
        run_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": record["status"], "image": pinned, "output": str(target)}))


if __name__ == "__main__":
    main()
