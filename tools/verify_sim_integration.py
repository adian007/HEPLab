"""Real-runtime acceptance smoke test, not independent cross-section validation."""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from heplab.io.provenance import config_hash
from heplab.readers.delphes import read
from heplab.sim.pipeline import run_chain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/sim-verification")
    args = parser.parse_args()
    root = Path(args.output)
    hashes = []
    summaries = []
    for name in ("repeat-a", "repeat-b"):
        output = run_chain(output=root / name, events=100, seed=42)
        rows = list(read(output / "events.root", source_id="fixed-shard"))
        assert len(rows) == 100
        assert all(event["Truth"] for event in rows)
        hashes.append(config_hash(rows))
        summaries.append(json.loads((output / "run.json").read_text())["summary"])
    assert hashes[0] == hashes[1], "physical event content must repeat for fixed build/cards/seeds"
    cancel = threading.Event()
    timer = threading.Timer(3, cancel.set)
    timer.start()
    try:
        try:
            run_chain(output=root / "cancelled", events=100000, seed=42, cancel=cancel)
        except RuntimeError as exc:
            assert "cancelled" in str(exc)
        else:
            raise AssertionError("cancelled simulation committed")
    finally:
        timer.cancel()
    assert not (root / "cancelled").exists()
    try:
        run_chain(output=root / "timeout", events=100000, timeout_s=1)
    except RuntimeError as exc:
        assert "timeout" in str(exc)
    else:
        raise AssertionError("timed out simulation committed")
    assert not (root / "timeout").exists()
    report = {
        "status": "passed",
        "events_per_repeat": 100,
        "physical_content_sha256": hashes,
        "fixed_shard_repeatable": True,
        "cancel_no_commit": True,
        "timeout_no_commit": True,
        "summaries": summaries,
        "independent_cross_section_validation": "pending",
    }
    (root / "verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
