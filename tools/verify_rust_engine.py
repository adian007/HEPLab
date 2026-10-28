"""Compare compiled Rust CLI and optional PyO3 extension to reference/analytic cases.

Pass --binary with the built CLI path and optionally --extension with the .so
path. Use --wsl Ubuntu when invoking Linux builds from Windows.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heplab.physics.engine import execute  # noqa: E402


def close(expected, actual):
    if isinstance(expected, dict):
        assert set(expected) == set(actual)
        for key in expected:
            close(expected[key], actual[key])
    elif isinstance(expected, (list, tuple)):
        assert len(expected) == len(actual)
        for left, right in zip(expected, actual, strict=True):
            close(left, right)
    elif isinstance(expected, (float, int)) and not isinstance(expected, bool):
        assert math.isclose(expected, actual, rel_tol=2e-11, abs_tol=2e-10), (expected, actual)
    else:
        assert expected == actual, (expected, actual)


def cases():
    rng = random.Random(314159)
    result = []
    for index in range(100):
        result.append(
            {
                "op": "mass",
                "first": [rng.uniform(1, 100), rng.uniform(-2, 2), rng.uniform(-3, 3), 0.105658],
                "second": [rng.uniform(1, 100), rng.uniform(-2, 2), rng.uniform(-3, 3), 0.105658],
            }
        )
        p = rng.uniform(0.1, 100)
        state = {
            "position": [0, 0, 0],
            "momentum": {"energy": math.hypot(p, 0.105658), "px": p, "py": 0, "pz": 0},
            "charge": (-1) ** index,
            "time_ns": 0,
        }
        result.append(
            {
                "op": "propagate",
                "state": state,
                "path_length_m": rng.uniform(0, 10),
                "bz_tesla": rng.choice([0, 1e-14, 2, -2]),
            }
        )
        result.append(
            {"op": "boost", "vector": state["momentum"], "beta": [rng.uniform(-0.5, 0.5), 0.1, 0.2]}
        )
        address = {
            "master_seed": 42,
            "event_key": f"event:{index}:\u03bc\U0001f680",
            "object_id": index,
            "stage_id": "resolution",
            "counter": 0,
            "model_id": "reference",
            "correlation_group": "nominal",
        }
        result.append({"op": "uniform", "address": address})
        result.append({"op": "normal", "address": address})
        result.append(
            {
                "op": "simulate",
                "particles": [{"object_id": index, "state": state}],
                "config": {
                    "seed": 42,
                    "event_key": "calibrated-parity",
                    "efficiency": 0.85,
                    "relative_pt_resolution": 0.02,
                    "momentum_scale": rng.uniform(0.99, 1.01),
                    "path_length_m": 0.0,
                    "bz_tesla": 0.0,
                    "max_objects": 1,
                },
            }
        )
        for surface in (
            {"kind": "cylinder", "radius_m": rng.uniform(0.01, 3), "half_length_m": 3.0},
            {"kind": "disk", "z_m": 1.0, "inner_radius_m": 0.0, "outer_radius_m": 3.0},
        ):
            moved = {**state, "position": [rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), -0.1]}
            result.append(
                {
                    "op": "intersect",
                    "state": moved,
                    "surface": surface,
                    "bz_tesla": rng.choice([0.0, 3.8, -3.8]),
                    "max_path_m": 10.0,
                }
            )
        result.append(
            {
                "op": "material",
                "state": state,
                "address": address,
                "slab": {
                    "id": "silicon",
                    "thickness_m": 0.001,
                    "radiation_length_m": 0.0937,
                    "stopping_power_gev_per_m": 0.4,
                    "min_beta_gamma": 0.5,
                    "max_beta_gamma": 1000.0,
                    "scatter": True,
                },
            }
        )
        result.append(
            {
                "op": "digitize",
                "deposit_gev": rng.uniform(0, 1),
                "address": address,
                "config": {
                    "gain_adc_per_gev": 1000.0,
                    "pedestal_adc": 1.0,
                    "noise_sigma_adc": 3.0,
                    "threshold_adc": 5.0,
                    "saturation_adc": 255.0,
                },
            }
        )
    result.append(
        {
            "op": "histogram",
            "edges": [0, 1, 2],
            "fills": [[-1, 1], [0, 2], [0.5, -2], [1, 3], [2, 4]],
        }
    )
    result.append(
        {"op": "histogram", "edges": [0, 1], "fills": [[0.5, 1e16], [0.5, 1], [0.5, -1e16]]}
    )
    state = {
        "position": [0, 0, 0],
        "momentum": {"energy": 5, "px": 3, "py": 0, "pz": 0},
        "charge": 1,
        "time_ns": 0,
    }
    result.append(
        {
            "op": "simulate",
            "particles": [{"object_id": i, "state": state} for i in range(30)],
            "config": {
                "seed": 42,
                "event_key": "toy",
                "efficiency": 0.8,
                "relative_pt_resolution": 0.05,
                "path_length_m": 2,
                "bz_tesla": 2,
                "max_objects": 100,
            },
        }
    )
    result.extend(
        [
            {"op": "boost", "vector": state["momentum"], "beta": [1, 0, 0]},
            {"op": "mass", "first": [-1, 0, 0, 1], "second": [1, 0, 0, 1]},
            {"op": "propagate", "state": state, "path_length_m": -1, "bz_tesla": 2},
            {"op": "histogram", "edges": [0, 0], "fills": []},
        ]
    )
    fixture = json.loads(
        (ROOT / "src/heplab/data/reference/cms-field-points.json").read_text(encoding="utf8")
    )
    result.extend({"op": "cms_tracker_field", "position_m": row[:3]} for row in fixture["points"])
    for charge in (-1, 0, 1):
        result.append(
            {
                "op": "trace_cms_tracker",
                "state": {
                    "position": [0.01, -0.03, 0.1],
                    "momentum": {"energy": math.hypot(1, 0.105658), "px": 1, "py": 0, "pz": 0},
                    "charge": charge,
                    "time_ns": 2,
                },
                "path_length_m": 0.6,
                "step_m": 0.005,
            }
        )
    result.extend(
        [
            {"op": "cms_tracker_field", "position_m": [1.15, 0, 0]},
            {"op": "cms_tracker_field", "position_m": [0, 0, 2.8]},
            {"op": "cms_tracker_field", "position_m": [True, 0, 0]},
        ]
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--wsl")
    parser.add_argument("--extension")
    args = parser.parse_args()
    inputs = cases()
    expected = []
    for request in inputs:
        try:
            expected.append({"ok": True, "result": execute(request)})
        except (ValueError, TypeError, KeyError, OverflowError):
            expected.append({"ok": False})
    wire = "".join(json.dumps(request, allow_nan=False) + "\n" for request in inputs)
    command = [args.binary]
    if args.wsl:
        command = ["wsl.exe", "-d", args.wsl, "--", args.binary]
    completed = subprocess.run(
        command, input=wire, capture_output=True, text=True, encoding="utf8", check=True, timeout=60
    )
    actual = [json.loads(line) for line in completed.stdout.splitlines()]
    assert len(actual) == len(expected)
    for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
        assert left["ok"] == right["ok"], (index, left, right)
        if left["ok"]:
            close(left["result"], right["result"])
    extension_cases = 0
    if args.extension:
        # Use the Python runtime matching the platform of the compiled extension.
        script = """import importlib.util,json,sys
from concurrent.futures import ThreadPoolExecutor
spec=importlib.util.spec_from_file_location("heplab_kernels",sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def run(line):
 try: return json.dumps({"ok":True,"result":json.loads(module.run_json(line))})
 except ValueError: return json.dumps({"ok":False})
with ThreadPoolExecutor(max_workers=4) as pool:
 for result in pool.map(run,list(sys.stdin)): print(result)
"""
        command = [sys.executable, "-c", script, args.extension]
        if args.wsl:
            command = ["wsl.exe", "-d", args.wsl, "--", "python3", "-c", script, args.extension]
        completed = subprocess.run(
            command,
            input=wire,
            capture_output=True,
            text=True,
            encoding="utf8",
            check=True,
            timeout=60,
        )
        actual = [json.loads(line) for line in completed.stdout.splitlines()]
        assert len(actual) == len(expected)
        for left, right in zip(expected, actual, strict=True):
            assert left["ok"] == right["ok"]
            if left["ok"]:
                close(left["result"], right["result"])
        extension_cases = len(actual)
    report = {
        "status": "passed",
        "cli_cases": len(inputs),
        "extension_cases": extension_cases,
        "extension_workers": 4 if args.extension else 0,
        "requirements": [
            "CORE-001",
            "CORE-002",
            "CORE-004",
            "CORE-005",
            "CORE-006",
            "CORE-007",
            "TRANSPORT-001",
        ],
        "scope": "analytic numerical core and educational response; no detector calibration claim",
    }
    target = ROOT / ".cache/rust-verification.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
