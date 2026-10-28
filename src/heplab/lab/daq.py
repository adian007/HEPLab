"""Loss-accounted raw-record decoding and clock unwrapping.

Raw files are immutable inputs: they are hashed before and after decoding and
never rewritten. ``heplab-synthetic-daq-v1`` is a documented test format used to
exercise the accounting; it is not the format of any real CMS or laboratory DAQ.
A decoder for real equipment needs that equipment's decoding specification.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from ..io.provenance import file_hash
from .profile import DeviceProfile

MAGIC = b"HLSYN001"
RECORD = struct.Struct(">BBIH")  # kind, channel, counter, payload
KINDS = {1: "hit", 2: "trigger", 3: "clock_reset", 4: "overflow", 5: "dead_start", 6: "dead_end"}
CODES = {name: code for code, name in KINDS.items()}


@dataclass(frozen=True)
class RawRecord:
    index: int
    offset: int
    kind: str
    channel: int
    counter: int
    payload: int


@dataclass
class DecodeLedger:
    """Every byte and record is either decoded or counted as a named loss."""

    bytes_total: int = 0
    records_read: int = 0
    records_decoded: int = 0
    invalid_kind: int = 0
    unmapped_channel: int = 0
    truncated_bytes: int = 0
    overflow_records: int = 0
    dropped_reported: int = 0
    clock_resets: int = 0
    invalid_offsets: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def write_fixture(path: str | Path, records: list[tuple[str, int, int, int]]) -> Path:
    """Write a synthetic fixture; refuses to overwrite so golden files stay immutable."""
    target = Path(path)
    with target.open("xb") as stream:
        stream.write(MAGIC)
        for kind, channel, counter, payload in records:
            stream.write(RECORD.pack(CODES.get(kind, 0xFF), channel, counter, payload))
    return target


def decode_synthetic(path: str | Path, profile: DeviceProfile) -> tuple[list[RawRecord], dict]:
    source = Path(path)
    before = file_hash(source)
    data = source.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f"{source}: not a heplab-synthetic-daq-v1 file")
    ledger = DecodeLedger(bytes_total=len(data))
    body = memoryview(data)[len(MAGIC) :]
    usable = len(body) - len(body) % RECORD.size
    ledger.truncated_bytes = len(body) - usable
    records: list[RawRecord] = []
    for index, start in enumerate(range(0, usable, RECORD.size)):
        ledger.records_read += 1
        code, channel, counter, payload = RECORD.unpack_from(body, start)
        offset = len(MAGIC) + start
        kind = KINDS.get(code)
        if kind is None:
            ledger.invalid_kind += 1
            ledger.invalid_offsets.append(offset)
            continue
        if kind == "hit" and channel not in profile.channels:
            ledger.unmapped_channel += 1
            ledger.invalid_offsets.append(offset)
            continue
        if kind == "overflow":
            ledger.overflow_records += 1
            ledger.dropped_reported += payload
        elif kind == "clock_reset":
            ledger.clock_resets += 1
        ledger.records_decoded += 1
        records.append(RawRecord(index, offset, kind, channel, counter, payload))
    if file_hash(source) != before:
        raise RuntimeError(f"{source}: raw file changed during decoding")
    accounted = ledger.records_decoded + ledger.invalid_kind + ledger.unmapped_channel
    if accounted != ledger.records_read:
        raise AssertionError("decode ledger does not account for every record")
    return records, {"format": "heplab-synthetic-daq-v1", "raw_sha256": before, **ledger.to_dict()}


@dataclass(frozen=True)
class TimedRecord:
    record: RawRecord
    epoch: int
    time_ns: float


def unwrap_clock(
    records: list[RawRecord], profile: DeviceProfile
) -> tuple[list[TimedRecord], dict]:
    """Unwrap a rolling counter into per-epoch times.

    A counter decrease is taken as exactly one rollover; longer silences cannot
    be distinguished from it by the counter alone, so the maximum unambiguous gap
    is reported. A clock reset starts a new epoch: times in different epochs are
    not comparable and are never merged into one event.
    """
    clock = profile.require_clock()
    period = 1 << clock["counter_bits"]
    tick = clock["tick_ns"]
    timed: list[TimedRecord] = []
    epoch, wraps, previous = 0, 0, None
    epochs: list[dict] = [{"epoch": 0, "rollovers": 0, "first_ns": None, "last_ns": None}]
    for record in records:
        if record.counter >= period:
            raise ValueError(f"record {record.index}: counter exceeds {clock['counter_bits']} bits")
        if record.kind == "clock_reset":
            epoch, wraps, previous = epoch + 1, 0, None
            epochs.append({"epoch": epoch, "rollovers": 0, "first_ns": None, "last_ns": None})
            continue
        if previous is not None and record.counter < previous:
            wraps += 1
            epochs[-1]["rollovers"] += 1
        previous = record.counter
        time_ns = (wraps * period + record.counter) * tick
        if epochs[-1]["first_ns"] is None:
            epochs[-1]["first_ns"] = time_ns
        epochs[-1]["last_ns"] = time_ns
        timed.append(TimedRecord(record, epoch, time_ns))
    return timed, {
        "tick_ns": tick,
        "counter_bits": clock["counter_bits"],
        "max_unambiguous_gap_ns": period * tick,
        "clock_source": clock["source"],
        "epochs": epochs,
    }


def live_time(timed: list[TimedRecord]) -> dict:
    """Per-epoch span minus declared dead time.

    Unmatched dead-time markers make live time an upper bound. Overflow does not
    change live time but means records were lost while live, so any rate or
    efficiency from that epoch is incomplete rather than a period without muons.
    """
    result = []
    for epoch in sorted({t.epoch for t in timed}):
        items = [t for t in timed if t.epoch == epoch]
        span = items[-1].time_ns - items[0].time_ns
        dead, start, unmatched = 0.0, None, 0
        for t in items:
            if t.record.kind == "dead_start":
                if start is not None:
                    unmatched += 1
                start = t.time_ns
            elif t.record.kind == "dead_end":
                if start is None:
                    unmatched += 1
                else:
                    dead += t.time_ns - start
                    start = None
        if start is not None:
            dead += items[-1].time_ns - start
            unmatched += 1
        overflow = any(t.record.kind == "overflow" for t in items)
        result.append(
            {
                "epoch": epoch,
                "span_ns": span,
                "dead_ns": dead,
                "live_ns": span - dead,
                "unmatched_dead_markers": unmatched,
                "live_time_is_upper_bound": unmatched > 0,
                "records_lost_while_live": overflow,
            }
        )
    return {"epochs": result, "live_ns_total": sum(e["live_ns"] for e in result)}
