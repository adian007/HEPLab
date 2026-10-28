"""Offline replay of recorded laboratory data into an auditable run record.

Replay never contacts hardware. Stages that need an unestablished quantity, such
as the DAQ clock, are reported as blocked instead of being run on assumptions.
"""

from __future__ import annotations

from pathlib import Path

from ..io.artifacts import publish
from ..io.provenance import config_hash, file_hash, source_snapshot
from . import daq, events
from .profile import UnknownQuantity, load_profile, profile_summary

RUN_SCHEMA = "heplab-lab-replay-run-v1"


def replay(
    profile_path: str | Path,
    raw_path: str | Path,
    output: str | Path,
    *,
    offsets_path: str | Path | None = None,
    window_ns: float = 25.0,
    trigger_source: str | None = None,
    conditions: dict | None = None,
) -> dict:
    profile = load_profile(profile_path)
    raw_sha = file_hash(raw_path)
    config = {
        "window_ns": window_ns,
        "trigger_source": trigger_source,
        "offsets_sha256": file_hash(offsets_path) if offsets_path else None,
    }
    stages: dict[str, dict] = {}
    records, stages["decode"] = daq.decode_synthetic(raw_path, profile)
    try:
        timed, stages["clock"] = daq.unwrap_clock(records, profile)
    except UnknownQuantity as exc:
        stages["clock"] = {"status": "blocked", "reason": str(exc)}
        timed = []
    if timed:
        stages["live_time"] = daq.live_time(timed)
        offsets = events.load_offsets(offsets_path, profile) if offsets_path else None
        hits, stages["calibration"] = events.correct_hits(timed, offsets)
        built, stages["events"] = events.build_events(hits, window_ns) if hits else ([], {})
        if trigger_source is not None:
            stages["efficiency"] = events.trigger_efficiency(
                timed, built, profile, trigger_source, window_ns
            )
    if file_hash(raw_path) != raw_sha:
        raise RuntimeError("raw file changed during replay")
    record = {
        "schema": RUN_SCHEMA,
        "hardware_contacted": False,
        "raw": {"name": Path(raw_path).name, "sha256": raw_sha},
        "profile": profile_summary(profile),
        "config": config,
        "config_sha256": config_hash(config),
        "conditions": conditions or {"state": "not recorded"},
        "source_tree_sha256": source_snapshot(),
        "stages": stages,
        "blocked_stages": sorted(k for k, v in stages.items() if v.get("status") == "blocked"),
    }
    publish(output, record)
    return record
