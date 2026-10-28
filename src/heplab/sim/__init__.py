"""Simulation helpers for toy studies and the external DELPHES container."""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from pathlib import Path

SIM_IMAGE = "ghcr.io/heplab/heplab-sim"


def _runtime(image):
    image = os.environ.get("HEPLAB_SIM_IMAGE", image)
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image):
        raise RuntimeError("simulation requires a locally built, pinned HEPLAB_SIM_IMAGE digest")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker runtime unavailable")
    result = subprocess.run(
        [docker, "image", "inspect", image], capture_output=True, text=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError("configured simulation image is not installed locally")
    return docker, image


def toy_smear(
    events: list[dict],
    *,
    relative_pt_resolution: float = 0.01,
    efficiency: float = 1.0,
    seed: int = 0,
) -> list[dict]:
    """Apply explicitly approximate Gaussian pT smearing and object efficiency."""
    if (
        not math.isfinite(relative_pt_resolution)
        or not math.isfinite(efficiency)
        or relative_pt_resolution < 0
        or not 0 <= efficiency <= 1
    ):
        raise ValueError("resolution must be nonnegative and efficiency must be in [0, 1]")
    from ..io.provenance import config_hash
    from ..physics.reference import addressed_normal, addressed_uniform

    sigma = math.sqrt(2 * math.log(math.hypot(relative_pt_resolution, 1)))
    output = []
    for source in events:
        info = source.get("EventInfo", {})
        if "event" not in info:
            raise ValueError("toy response needs a stable event identity")
        event_key = config_hash(
            {
                k: info.get(k)
                for k in ("run", "luminosity_block", "event", "source_id", "source_entry")
            }
        )
        event = {key: value for key, value in source.items()}
        for collection in ("Muon", "Electron", "Photon", "Jet"):
            objects = []
            for index, original in enumerate(source.get(collection) or []):
                identity = original.get("object_id", index)
                address = {"master_seed": seed, "event_key": event_key, "object_id": identity}
                if addressed_uniform(**address, stage_id=f"{collection}.efficiency") >= efficiency:
                    continue
                obj = dict(original)
                pt = float(obj["pt"])
                if not math.isfinite(pt) or pt < 0:
                    raise ValueError("invalid truth transverse momentum")
                obj["pt"] = pt * math.exp(
                    sigma * addressed_normal(**address, stage_id=f"{collection}.resolution")
                    - 0.5 * sigma * sigma
                )
                objects.append(obj)
            event[collection] = objects
        event["EventInfo"] = {**source.get("EventInfo", {}), "is_data": False}
        event["Simulation"] = {
            "model": "educational-lognormal-v1",
            "seed": seed,
            "validation": "unvalidated",
        }
        output.append(event)
    return output


def generate(
    *,
    output: str = "data/generated.hepmc",
    events: int = 10_000,
    seed: int = 42,
    image: str = SIM_IMAGE,
) -> Path:
    """Run the project simulation image; the image supplies Pythia8 and cards."""
    if type(events) is not int or events <= 0 or type(seed) is not int or not 0 <= seed < 2**31:
        raise ValueError("invalid generator event budget or seed")
    docker, image = _runtime(image)
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{target.parent}:/output",
            image,
            "generate",
            "--events",
            str(events),
            "--seed",
            str(seed),
            "--output",
            f"/output/{target.name}",
        ],
        check=True,
    )
    return target


def simulate(*, input: str, output: str = "data/delphes.root", image: str = SIM_IMAGE) -> Path:
    docker, image = _runtime(image)
    source, target = Path(input).resolve(), Path(output).resolve()
    if not source.is_file():
        raise ValueError("simulation input file does not exist")
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "-v",
            f"{source.parent}:/input:ro",
            "-v",
            f"{target.parent}:/output",
            image,
            "simulate",
            "--input",
            f"/input/{source.name}",
            "--output",
            f"/output/{target.name}",
        ],
        check=True,
    )
    return target
