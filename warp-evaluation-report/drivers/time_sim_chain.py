"""Stage-2 regime evidence: PYTHIA8/DELPHES sim chain wall time.

The registered `heplab sim chain` path never calls the engine seams
(sim/pipeline.py and analyses/collision contain no engine.execute call —
verified by grep before measuring). This driver records the stage wall time
at the registered minimum scale (events=100, seed=42) so the report can state
the seam share of this regime as a structural fact backed by one measurement.

Run: python time_sim_chain.py <repo-root> <results-dir>
"""

from __future__ import annotations

import json
import platform
import socket
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
RESULTS = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else REPO / "warp-evaluation-report" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / "src"))


def main() -> None:
    from heplab.sim.pipeline import run_chain

    with tempfile.TemporaryDirectory(prefix="warp-eval-chain-") as temporary:
        started = time.perf_counter()
        destination = run_chain(output=Path(temporary) / "chain", events=100, seed=42)
        elapsed = time.perf_counter() - started
        summary = json.loads((destination / "run.json").read_text(encoding="utf8")).get("summary", {})

    payload = {
        "driver": "drivers/time_sim_chain.py",
        "entry_point": "heplab.sim.pipeline.run_chain",
        "events": 100,
        "seed": 42,
        "wall_s": elapsed,
        "summary_from_run_json": summary,
        "engine_seam_calls_on_path": 0,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "host": socket.gethostname(),
            "sim_runtime": "WSL Ubuntu prefix ~/.cache/heplab/sim-runtime (PYTHIA 8.312, DELPHES 3.5.1, ROOT 6.40.04)",
        },
    }
    (RESULTS / "sim-chain-time.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
