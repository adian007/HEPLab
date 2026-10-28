"""Channel time corrections, coincidence event building and denominated efficiency.

Each stage is separate and reproducible. Efficiency is only defined against an
independent trigger declared in the device profile; self-triggered hits cannot
supply a denominator.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .daq import TimedRecord
from .profile import DeviceProfile, ProfileError

OFFSETS_SCHEMA = "heplab-lab-channel-offsets-v1"


def load_offsets(path: str | Path, profile: DeviceProfile) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != OFFSETS_SCHEMA:
        raise ProfileError(f"channel offsets schema must be {OFFSETS_SCHEMA}")
    if raw.get("profile_sha256") != profile.digest:
        raise ProfileError("channel offsets were derived for a different device profile")
    if not raw.get("source"):
        raise ProfileError("channel offsets need a source calibration run")
    offsets = {int(channel): float(value) for channel, value in raw["offsets_ns"].items()}
    missing = sorted(set(profile.channels) - set(offsets))
    if missing:
        # A missing channel is not a zero offset.
        raise ProfileError(f"channel offsets missing for channels {missing}")
    if not all(math.isfinite(value) for value in offsets.values()):
        raise ProfileError("channel offsets must be finite")
    return {"offsets_ns": offsets, "source": raw["source"]}


@dataclass(frozen=True)
class Hit:
    record_index: int
    epoch: int
    channel: int
    time_ns: float
    payload: int


def correct_hits(timed: list[TimedRecord], offsets: dict | None) -> tuple[list[Hit], dict]:
    table = offsets["offsets_ns"] if offsets else {}
    hits = [
        Hit(
            t.record.index,
            t.epoch,
            t.record.channel,
            t.time_ns - table.get(t.record.channel, 0.0),
            t.record.payload,
        )
        for t in timed
        if t.record.kind == "hit"
    ]
    return hits, {
        "channel_offsets": "applied" if offsets else "not applied: uncalibrated channel timing",
        "offsets_source": offsets["source"] if offsets else None,
        "hits": len(hits),
    }


def build_events(hits: list[Hit], window_ns: float) -> tuple[list[dict], dict]:
    """Group hits whose times lie within ``window_ns`` of the event's first hit."""
    if not window_ns > 0:
        raise ValueError("coincidence window must be positive")
    events: list[dict] = []
    for epoch in sorted({h.epoch for h in hits}):
        current: list[Hit] = []
        for hit in sorted((h for h in hits if h.epoch == epoch), key=lambda h: h.time_ns):
            if current and hit.time_ns - current[0].time_ns > window_ns:
                events.append(_event(len(events), current))
                current = []
            current.append(hit)
        if current:
            events.append(_event(len(events), current))
    assigned = sum(len(e["record_indices"]) for e in events)
    if assigned != len(hits):
        raise AssertionError("event building lost or duplicated hits")
    return events, {
        "window_ns": window_ns,
        "events": len(events),
        "hits_assigned": assigned,
        "multiplicity": _histogram(len(e["channels"]) for e in events),
    }


def _event(number: int, hits: list[Hit]) -> dict:
    return {
        "event": number,
        "epoch": hits[0].epoch,
        "time_ns": hits[0].time_ns,
        "channels": sorted({h.channel for h in hits}),
        "record_indices": [h.record_index for h in hits],
    }


def _histogram(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: int(item[0])))


def dead_intervals(timed: list[TimedRecord]) -> list[tuple[int, float, float]]:
    intervals, open_at = [], {}
    for t in timed:
        if t.record.kind == "dead_start":
            open_at[t.epoch] = t.time_ns
        elif t.record.kind == "dead_end" and t.epoch in open_at:
            intervals.append((t.epoch, open_at.pop(t.epoch), t.time_ns))
    last = {t.epoch: t.time_ns for t in timed}
    intervals.extend((epoch, start, last[epoch]) for epoch, start in open_at.items())
    return intervals


def trigger_efficiency(
    timed: list[TimedRecord],
    events: list[dict],
    profile: DeviceProfile,
    trigger_source: str,
    window_ns: float,
) -> dict:
    """Fraction of independent triggers with a detector event within the window.

    Without external track positions there is no active-area selection, so this
    is a trigger-denominated efficiency, not an active-area chamber efficiency.
    """
    declared = profile.trigger_sources.get(trigger_source)
    if declared is None:
        raise ProfileError(f"trigger source {trigger_source!r} is not declared in the profile")
    if not declared["independent"]:
        raise ProfileError(
            f"trigger source {trigger_source!r} is not independent of the detector; "
            "self-triggered data cannot define an efficiency denominator"
        )
    dead = dead_intervals(timed)
    triggers = [
        t for t in timed if t.record.kind == "trigger" and str(t.record.payload) == trigger_source
    ]
    live = [
        t for t in triggers if not any(e == t.epoch and lo <= t.time_ns <= hi for e, lo, hi in dead)
    ]
    matched = sum(
        any(e["epoch"] == t.epoch and abs(e["time_ns"] - t.time_ns) <= window_ns for e in events)
        for t in live
    )
    n = len(live)
    return {
        "trigger_source": trigger_source,
        "trigger_description": declared["description"],
        "triggers_seen": len(triggers),
        "excluded_in_dead_time": len(triggers) - n,
        "denominator": n,
        "numerator": matched,
        "efficiency": matched / n if n else None,
        "wilson_68": _wilson(matched, n) if n else None,
        "match_window_ns": window_ns,
        "active_area_selection": "not applied: requires external track positions",
        "claim": "trigger-denominated relative efficiency; not an active-area chamber efficiency",
    }


def _wilson(k: int, n: int, z: float = 1.0) -> list[float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [max(0.0, centre - half), min(1.0, centre + half)]
