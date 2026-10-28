"""Verify the compiled Rust bridge against CMS points and DOP853 transport."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from heplab.physics.cms_field import tracker_field
from heplab.physics.reference import FourVector, TrackState

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl", default="Ubuntu")
    parser.add_argument(
        "--executable", default="/mnt/d/CERN/kernels/physics-core/target/release/heplab-physics"
    )
    args = parser.parse_args()
    source = ROOT / "artifacts/cms/field/referenceField_160812_RII_3_8T.bin"
    if hashlib.sha256(source.read_bytes()).hexdigest() != (
        "b785fa7a7a16b9dbbbabaf7751bd64e0cb7a15a0e51fcd9c60aa4263bde90e8b"
    ):
        raise ValueError("CMS reference changed")
    points = np.fromfile(source, dtype="<f4").reshape(-1, 6).astype(float)
    points[:, :3] /= 100
    points = points[(np.hypot(points[:, 0], points[:, 1]) < 1.15) & (abs(points[:, 2]) < 2.8)]
    requests = [{"op": "cms_tracker_field", "position_m": row[:3].tolist()} for row in points]
    states = []
    for charge in [-1, 0, 1]:
        for pt, eta in [(0.4, 0.8), (1.0, -0.7), (45.0, 0.1)]:
            state = TrackState(
                (0.01, -0.03, 0.1),
                FourVector.from_pt_eta_phi_mass(pt, eta, 0.7, 0.10565839),
                charge,
                2,
            )
            states.append(state)
            requests.append(
                {
                    "op": "trace_cms_tracker",
                    "state": asdict(state),
                    "path_length_m": 0.6,
                    "step_m": 0.005,
                }
            )
    result = subprocess.run(
        ["wsl.exe", "-d", args.wsl, "--", args.executable],
        input="".join(json.dumps(r) + "\n" for r in requests),
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    if len(responses) != len(requests) or not all(row["ok"] for row in responses):
        raise ValueError("compiled Rust protocol rejected a valid reference request")
    values = np.array([r["result"] for r in responses[: len(points)]])
    field_error = float(np.max(np.linalg.norm(values - points[:, 3:], axis=1)))
    position_error, momentum_error = 0.0, 0.0
    for state, response in zip(states, responses[len(points) :], strict=True):

        def derivative(_s, y, charge=state.charge):
            u = y[3:] / np.linalg.norm(y[3:])
            return np.concatenate(
                (u, 0.299792458 * charge * np.cross(u, tracker_field(y[:3].tolist())))
            )

        p = state.momentum
        expected = solve_ivp(
            derivative,
            (0, 0.6),
            [*state.position, p.px, p.py, p.pz],
            method="DOP853",
            rtol=1e-12,
            atol=1e-13,
        ).y[:, -1]
        actual = response["result"]["state"]
        position_error = max(position_error, math.dist(expected[:3], actual["position"]))
        momentum_error = max(
            momentum_error,
            math.dist(expected[3:], [actual["momentum"][k] for k in ["px", "py", "pz"]]),
        )
    report = {
        "cms_field_points": len(points),
        "max_field_vector_error_t": field_error,
        "field_gate_t": 2e-6,
        "dop853_transport_cases": len(states),
        "max_position_error_m": position_error,
        "position_gate_m": 2e-9,
        "max_momentum_error_gev": momentum_error,
        "momentum_gate_gev": 2e-9,
        "passed": field_error < 2e-6 and position_error < 2e-9 and momentum_error < 2e-9,
    }
    (ROOT / "artifacts/cms/rust-verification.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf8"
    )
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit("CMS model verification failed")


if __name__ == "__main__":
    main()
