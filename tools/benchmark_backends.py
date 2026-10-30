"""Small fixed-fixture Python/Rust semantic microbenchmark, not a product workload claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from heplab.physics.constants import MUON_MASS_GEV
from heplab.physics.engine import capabilities, execute

ROOT = Path(__file__).resolve().parents[1]
STATE = {
    "position": [0.0, 0.0, 0.0],
    "momentum": {"energy": math.hypot(20.0, MUON_MASS_GEV), "px": 20.0, "py": 0.0, "pz": 0.0},
    "charge": 1.0,
    "time_ns": 0.0,
}
ADDRESS = {
    "master_seed": 8821,
    "event_key": "fixed-backend-microbenchmark-v1",
    "object_id": 3,
    "stage_id": "material",
    "counter": 0,
    "correlation_group": "nominal",
    "model_id": "thin-slab-highland-v1",
}
FIXTURES = {
    "mass": {
        "op": "mass",
        "first": [45.0, 0.2, 0.0, MUON_MASS_GEV],
        "second": [45.0, -0.2, math.pi, MUON_MASS_GEV],
    },
    "propagate": {"op": "propagate", "state": STATE, "path_length_m": 1.0, "bz_tesla": 3.8},
    "material": {
        "op": "material",
        "state": STATE,
        "slab": {
            "id": "benchmark-silicon-slab",
            "thickness_m": 0.001,
            "radiation_length_m": 0.0937,
            "stopping_power_gev_per_m": 0.507,
            "min_beta_gamma": 1.0,
            "max_beta_gamma": 1000.0,
            "scatter": True,
        },
        "address": ADDRESS,
    },
}


def digest(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def close(a: Any, b: Any, path: str = "result") -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close(a[k], b[k], f"{path}.{k}") for k in a)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return len(a) == len(b) and all(
            close(x, y, f"{path}[{i}]") for i, (x, y) in enumerate(zip(a, b, strict=True))
        )
    if (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    ):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-10)
    return a == b


def measure(request: dict[str, Any], backend: str, warmup: int, repeats: int) -> dict[str, float]:
    for _ in range(warmup):
        execute(request, backend=backend)
    timings = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        execute(request, backend=backend)
        timings.append((time.perf_counter_ns() - start) / 1e6)
    ordered = sorted(timings)
    return {
        "repeats": repeats,
        "median_ms": statistics.median(timings),
        "p95_ms": ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)],
        "min_ms": min(timings),
        "max_ms": max(timings),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=200)
    args = parser.parse_args()
    if args.warmup < 0 or args.repeats < 10:
        parser.error("--warmup must be nonnegative and --repeats at least 10")
    rust_available = capabilities()["rust_extension"]
    results = {}
    for name, request in FIXTURES.items():
        reference = execute(request, backend="reference")
        row = {
            "request_sha256": digest(request),
            "reference_output_sha256": digest(reference),
            "reference": measure(request, "reference", args.warmup, args.repeats),
            "rust": None,
            "semantic_parity": "not_run_rust_unavailable",
        }
        if rust_available:
            native = execute(request, backend="rust")
            row["rust_output_sha256"] = digest(native)
            row["semantic_parity"] = "pass" if close(reference, native) else "fail"
            row["rust"] = measure(request, "rust", args.warmup, args.repeats)
        results[name] = row
    report = {
        "schema": "heplab-fixed-backend-microbenchmark-v1",
        "purpose": (
            "fixed semantic fixtures and wrapper-inclusive operation latency; "
            "not representative end-to-end throughput"
        ),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor() or None,
            "machine": platform.machine(),
            "rust_extension_available": rust_available,
            "rust_executable_configured": capabilities()["rust_executable_configured"],
        },
        "workload": {
            "warmup": args.warmup,
            "repeats": args.repeats,
            "fixtures": sorted(FIXTURES),
            "fixture_set_sha256": digest(FIXTURES),
            "timing": (
                "perf_counter_ns; each sample times one execute() call including "
                "request validation/serialization"
            ),
            "uncertainty": (
                "median and empirical 95th percentile over repeated single-call timings; "
                "no claim of deployment performance"
            ),
        },
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
