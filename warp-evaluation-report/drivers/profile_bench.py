"""Stage-2 profile driver: workbench analytic bench through the public boundary.

Measures the user-visible stage exactly as `heplab.server.workbench.Jobs._run`
runs it (bench event loop + analyze_events, no persistence), at the largest
GUI-allowed scale (RunConfig: angular_sample, events=200, reference backend,
default response model). Variants isolate the candidate seams:

- V0 full:         real trajectory/execute/calibration work
- V1 no_transport: trajectory/tracker_trajectory stubbed (transport+crossing free)
- V2 floor:        additionally execute + silicon_stopping_power stubbed
                   (engine work and per-track calibration reads removed)

Also times the GUI event-navigation regime: one muon_display call per
displayed event (two reconstructed muons), which is the per-click path.

Writes results/bench-reference-profile.json and a cProfile census text.
Run: python profile_bench.py <repo-root> <results-dir>
"""

from __future__ import annotations

import cProfile
import io
import json
import platform
import pstats
import sys
import threading
import time
from pathlib import Path

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
RESULTS = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else REPO / "warp-evaluation-report" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "src"))

CANCEL = threading.Event()


def stub_trajectory(state, *, bz=3.8, max_path=16.0, step=0.05, backend="reference"):
    position = [float(v) for v in state.position]
    return {
        "points": [position, position],
        "path_m": [0.0, float(max_path)],
        "crossings": [],
        "field_exit_path_m": None,
        "field_bz_tesla": float(bz),
        "termination": "stub",
        "geometry_sha256": "stub",
        "model": "stub",
        "validation": "stub",
        "navigation_backend": backend,
    }


def stub_tracker_trajectory(state, max_path, backend="reference"):
    payload = stub_trajectory(state, max_path=max_path, backend=backend)
    payload.update(
        actual_path_m=float(max_path),
        crossing_method="stub",
        field_model="stub",
    )
    return payload


def stub_execute(request, *, backend="reference"):
    op = request["op"]
    if op == "propagate":
        return dict(request["state"])
    if op == "material":
        return {
            "state": dict(request["state"]),
            "deposit_gev": 0.0,
            "theta0_rad": 0.0,
            "energy_residual_gev": 0.0,
        }
    if op == "digitize":
        return {
            "adc": 1,
            "accepted": True,
            "saturated": False,
            "analog_adc": 1.0,
            "deposit_gev": request["deposit_gev"],
        }
    if op == "simulate":
        return {
            "objects": [],
            "input_objects": len(request["particles"]),
            "accepted_objects": 0,
        }
    raise ValueError(op)


def stub_stopping_power(kinetic_gev):
    return 0.4, {
        "id": "stub",
        "source_sha256": "0" * 64,
        "scope": "stub",
        "kinetic_gev": kinetic_gev,
        "heldout_max_relative_error": 0.0,
    }


def run_stage(workbench, config, count):
    from heplab.server.workbench import analyze_events

    started = time.perf_counter()
    for index in range(count):
        event = workbench.bench(config, CANCEL, index)
        analyze_events([event])
    return time.perf_counter() - started


def main() -> None:
    import heplab.server.workbench as workbench
    from heplab.server.workbench import RunConfig, muon_display

    config = RunConfig(
        source_model="angular_sample",
        events=200,
        seed=42,
    )
    assert config.events == 200  # GUI limit for angular samples, per RunConfig validator
    count = config.events

    workbench.bench(config, CANCEL, 0)  # warm-up event, discarded (imports, calibration cache)

    timings = {}

    timings["V0_full_s"] = run_stage(workbench, config, count)

    original_trajectory = workbench.trajectory
    original_tracker = workbench.tracker_trajectory
    workbench.trajectory = stub_trajectory
    workbench.tracker_trajectory = stub_tracker_trajectory
    try:
        timings["V1_no_transport_s"] = run_stage(workbench, config, count)

        original_execute = workbench.execute
        original_stopping = workbench.silicon_stopping_power
        workbench.execute = stub_execute
        workbench.silicon_stopping_power = stub_stopping_power
        try:
            timings["V2_floor_s"] = run_stage(workbench, config, count)
        finally:
            workbench.execute = original_execute
            workbench.silicon_stopping_power = original_stopping
    finally:
        workbench.trajectory = original_trajectory
        workbench.tracker_trajectory = original_tracker

    # cProfile census of the full variant, single run.
    profiler = cProfile.Profile()
    profiler.enable()
    run_stage(workbench, config, count)
    profiler.disable()
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs().sort_stats("cumulative").print_stats(30)
    stream.write("\n--- by internal time ---\n")
    stats.sort_stats("tottime").print_stats(30)
    (RESULTS / "bench-reference-cprofile.txt").write_text(stream.getvalue(), encoding="utf-8")

    # GUI regime: one muon_display call per displayed event (per-click latency).
    muons = [
        {"object_id": 0, "pt": 30.0, "eta": 0.5, "phi": 0.4, "charge": 1},
        {"object_id": 1, "pt": 30.0, "eta": -0.5, "phi": 0.4 + 3.14159, "charge": -1},
    ]
    for _ in range(3):
        muon_display(muons, 0)  # warm-up, discarded
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        muon_display(muons, 0)
        samples.append((time.perf_counter() - started) * 1000.0)
    timings["gui_muon_display_ms"] = {
        "calls": len(samples),
        "min_ms": min(samples),
        "mean_ms": sum(samples) / len(samples),
        "max_ms": max(samples),
    }

    payload = {
        "driver": "drivers/profile_bench.py",
        "entry_point": "heplab.server.workbench.Jobs._run analytic loop (bench + analyze_events)",
        "config": config.model_dump(),
        "events": count,
        "tracks_per_event": 2,
        "timings": timings,
        "derived": {
            "transport_share": (
                (timings["V0_full_s"] - timings["V1_no_transport_s"]) / timings["V0_full_s"]
            ),
            "engine_ops_and_calibration_share": (
                (timings["V1_no_transport_s"] - timings["V2_floor_s"]) / timings["V0_full_s"]
            ),
            "free_transport_ceiling_ratio": timings["V0_full_s"] / timings["V1_no_transport_s"],
            "free_engine_ceiling_ratio": timings["V0_full_s"] / timings["V2_floor_s"],
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": __import__("os").cpu_count(),
            "gpu": "Intel Arc 140V (no CUDA device present)",
        },
    }
    (RESULTS / "bench-reference-profile.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
