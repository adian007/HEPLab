"""Protocol-conformant B1/B2 measurement driver (imports the skill's measure.py).

Parent mode re-runs itself in a fresh process per case (measure.run_isolated);
each child emits one JSONL record carrying the measure.py `env` fingerprint.
Cases (pass as argv[4:]):

  V0_full           200-event analytic bench stage, reference backend
  V1_no_transport   trajectory/tracker_trajectory stubbed
  V2_floor          additionally execute + silicon_stopping_power stubbed
  V0_rust           same stage with backend="rust" (requires heplab_kernels)
  B2_muon_display   one muon_display call (GUI per-click regime)

Run:
  python measure_b1_stage.py <repo-root> <warp-eval-skill-scripts-dir> <results-file> CASE [CASE...]
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

# In a run_isolated child there is no argv: configuration arrives via
# WARP_EVAL_* environment variables passed through extra_env.
if os.environ.get("WARP_EVAL_CASE"):
    REPO = Path(os.environ["WARP_EVAL_REPO"]).resolve()
    SKILL_SCRIPTS = Path(os.environ["WARP_EVAL_SKILL"]).resolve()
    RESULTS_FILE = None
    CASES = []
else:
    REPO = Path(sys.argv[1]).resolve()
    SKILL_SCRIPTS = Path(sys.argv[2]).resolve()
    RESULTS_FILE = Path(sys.argv[3]).resolve()
    CASES = sys.argv[4:]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(SKILL_SCRIPTS))

import measure  # noqa: E402  (skill measurement primitives)

CANCEL = threading.Event()
EVENTS = 200


def _stub_trajectory(state, *, bz=3.8, max_path=16.0, step=0.05, backend="reference"):
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


def _stub_tracker_trajectory(state, max_path, backend="reference"):
    payload = _stub_trajectory(state, max_path=max_path, backend=backend)
    payload.update(actual_path_m=float(max_path), crossing_method="stub", field_model="stub")
    return payload


def _stub_execute(request, *, backend="reference"):
    op = request["op"]
    if op == "propagate":
        return dict(request["state"])
    if op == "material":
        return {"state": dict(request["state"]), "deposit_gev": 0.0, "theta0_rad": 0.0, "energy_residual_gev": 0.0}
    if op == "digitize":
        return {
            "adc": 1,
            "accepted": True,
            "saturated": False,
            "analog_adc": 1.0,
            "deposit_gev": request["deposit_gev"],
        }
    if op == "simulate":
        return {"objects": [], "input_objects": len(request["particles"]), "accepted_objects": 0}
    raise ValueError(op)


def _stub_stopping_power(kinetic_gev):
    return 0.4, {
        "id": "stub",
        "source_sha256": "0" * 64,
        "scope": "stub",
        "kinetic_gev": kinetic_gev,
        "heldout_max_relative_error": 0.0,
    }


def _stage(workbench, config):
    from heplab.server.workbench import analyze_events

    def run():
        for index in range(config.events):
            analyze_events([workbench.bench(config, CANCEL, index)])

    return run


def run_case(case: str) -> dict:
    import heplab.server.workbench as workbench
    from heplab.server.workbench import RunConfig, muon_display

    record: dict = {"case": case}
    if case == "B2_muon_display":
        muons = [
            {"object_id": 0, "pt": 30.0, "eta": 0.5, "phi": 0.4, "charge": 1},
            {"object_id": 1, "pt": 30.0, "eta": -0.5, "phi": 0.4 + 3.14159, "charge": -1},
        ]
        record.update(measure.time_it(lambda: muon_display(muons, 0), device=None))
        record.update(memory=measure.host_memory())
        return record

    backend = "rust" if case == "V0_rust" else "reference"
    config = RunConfig(source_model="angular_sample", events=EVENTS, seed=42, backend=backend)
    workbench.bench(config, CANCEL, 0)  # warm-up outside the timed region as well

    original_trajectory, original_tracker = workbench.trajectory, workbench.tracker_trajectory
    original_execute, original_stopping = workbench.execute, workbench.silicon_stopping_power
    try:
        if case in ("V1_no_transport", "V2_floor"):
            workbench.trajectory = _stub_trajectory
            workbench.tracker_trajectory = _stub_tracker_trajectory
        if case == "V2_floor":
            workbench.execute = _stub_execute
            workbench.silicon_stopping_power = _stub_stopping_power
        record.update(measure.time_it(_stage(workbench, config), device=None))
        record.update(memory=measure.host_memory())
    finally:
        workbench.trajectory, workbench.tracker_trajectory = original_trajectory, original_tracker
        workbench.execute, workbench.silicon_stopping_power = original_execute, original_stopping
    return record


def main() -> None:
    case = measure.isolated_case()
    if case:
        measure.emit(None, run_case(case))
        return

    if not CASES:
        raise SystemExit("no cases given")

    def make_stage(k: int):
        import heplab.server.workbench as workbench
        from heplab.server.workbench import RunConfig

        config = RunConfig(source_model="angular_sample", events=k, seed=42)
        return _stage(workbench, config)

    harness = measure.null_test(make_stage, device=None, scale=4)
    measure.emit(RESULTS_FILE, {"case": "null_test", **harness})
    for name in CASES:
        record = measure.run_isolated(
            name,
            script=__file__,
            extra_env={"WARP_EVAL_REPO": str(REPO), "WARP_EVAL_SKILL": str(SKILL_SCRIPTS)},
        )
        measure.emit(RESULTS_FILE, record)


if __name__ == "__main__":
    main()
