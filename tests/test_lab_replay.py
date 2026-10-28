"""Laboratory profile and offline replay contracts (LAB-001/002/003/004/007/008).

The DAQ fixture is the synthetic heplab test format, not any real detector's
format; these tests exercise accounting and guards, not device physics.
"""

import copy
import json
from pathlib import Path

import pytest

from heplab.cli import main
from heplab.lab import daq, events
from heplab.lab.profile import (
    ProfileError,
    UnknownQuantity,
    load_profile,
    parse_profile,
)
from heplab.lab.replay import replay

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts/examples/lab-device-profile.json"
INTAKE = ROOT / "manifests/lab/cms-muon-box-intake.json"

# 8-bit counter, 1 ns tick: the counter rolls over once after 250 -> 3.
RECORDS = [
    ("hit", 0, 10, 0),
    ("trigger", 0, 12, 1),
    ("hit", 1, 14, 0),
    ("dead_start", 0, 100, 0),
    ("trigger", 0, 110, 1),
    ("dead_end", 0, 120, 0),
    ("hit", 0, 250, 0),
    ("trigger", 0, 3, 1),
    ("hit", 1, 5, 0),
    ("trigger", 0, 100, 1),
    ("bogus", 0, 101, 0),
    ("hit", 7, 102, 0),
    ("overflow", 0, 103, 3),
    ("trigger", 0, 104, 9),
    ("clock_reset", 0, 0, 0),
    ("hit", 0, 40, 0),
    ("trigger", 0, 41, 1),
]


@pytest.fixture
def raw(tmp_path):
    path = daq.write_fixture(tmp_path / "run.bin", RECORDS)
    with path.open("ab") as stream:
        stream.write(b"\x01\x00\x00")  # truncated trailing record
    return path


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_intake_profile_keeps_reported_and_unknown_values_unusable():
    profile = load_profile(INTAKE)
    assert profile.identification == "unidentified"
    assert not profile.control_permitted
    with pytest.raises(UnknownQuantity):
        profile.length_cm("enclosure_height")
    with pytest.raises(UnknownQuantity):
        profile.require("device_type")
    with pytest.raises(UnknownQuantity):
        profile.require_clock()
    assert {"channel_map", "clock", "device_type", "enclosure_height"} <= set(profile.unknowns())


def test_identified_profile_requires_identity_and_control_requires_approval():
    raw = example()
    raw["quantities"]["serial_number"] = {"state": "unknown"}
    with pytest.raises(ProfileError, match="serial_number"):
        parse_profile(raw)
    raw = example()
    raw["control"] = {"permitted": True}
    with pytest.raises(ProfileError, match="operator"):
        parse_profile(raw)
    raw = example()
    raw["quantities"]["active_length"] = {"state": "unknown", "value": 3}
    with pytest.raises(ProfileError, match="cannot carry values"):
        parse_profile(raw)
    assert parse_profile(example()).length_cm("active_length") == 100.0


def test_decode_accounts_for_every_record_and_byte(raw):
    records, ledger = daq.decode_synthetic(raw, parse_profile(example()))
    assert ledger["records_read"] == 17
    assert ledger["records_decoded"] == 15 == len(records)
    assert ledger["invalid_kind"] == 1
    assert ledger["unmapped_channel"] == 1
    assert ledger["truncated_bytes"] == 3
    assert ledger["dropped_reported"] == 3
    assert ledger["clock_resets"] == 1
    assert ledger["bytes_total"] == len(daq.MAGIC) + 17 * daq.RECORD.size + 3


def test_clock_unwrap_rollover_epochs_and_live_time(raw):
    profile = parse_profile(example())
    timed, clock = daq.unwrap_clock(daq.decode_synthetic(raw, profile)[0], profile)
    assert [e["rollovers"] for e in clock["epochs"]] == [1, 0]
    assert clock["max_unambiguous_gap_ns"] == 256.0
    assert [t.time_ns for t in timed if t.record.kind == "hit"] == [10, 14, 250, 261, 40]
    live = daq.live_time(timed)["epochs"]
    assert live[0] == {
        "epoch": 0,
        "span_ns": 350.0,
        "dead_ns": 20.0,
        "live_ns": 330.0,
        "unmatched_dead_markers": 0,
        "live_time_is_upper_bound": False,
        "records_lost_while_live": True,
    }
    assert live[1]["live_ns"] == 1.0


def test_events_do_not_cross_epochs_and_efficiency_needs_independent_trigger(raw):
    profile = parse_profile(example())
    timed, _ = daq.unwrap_clock(daq.decode_synthetic(raw, profile)[0], profile)
    hits, calibration = events.correct_hits(timed, None)
    assert calibration["channel_offsets"].startswith("not applied")
    built, summary = events.build_events(hits, 25.0)
    assert [(e["epoch"], e["channels"]) for e in built] == [(0, [0, 1]), (0, [0, 1]), (1, [0])]
    assert summary["multiplicity"] == {"1": 1, "2": 2}
    result = events.trigger_efficiency(timed, built, profile, "1", 25.0)
    assert (result["triggers_seen"], result["excluded_in_dead_time"]) == (5, 1)
    assert (result["numerator"], result["denominator"]) == (3, 4)
    low, high = result["wilson_68"]
    assert low < 0.75 < high
    with pytest.raises(ProfileError, match="not independent"):
        events.trigger_efficiency(timed, built, profile, "9", 25.0)
    with pytest.raises(ProfileError, match="not declared"):
        events.trigger_efficiency(timed, built, profile, "2", 25.0)


def test_channel_offsets_must_match_profile_and_cover_all_channels(tmp_path):
    profile = parse_profile(example())
    offsets = {
        "schema": events.OFFSETS_SCHEMA,
        "profile_sha256": profile.digest,
        "source": "synthetic calibration run",
        "offsets_ns": {"0": 0.0, "1": 4.0},
    }
    path = tmp_path / "offsets.json"
    path.write_text(json.dumps(offsets), encoding="utf-8")
    assert events.load_offsets(path, profile)["offsets_ns"] == {0: 0.0, 1: 4.0}
    for change in ({"offsets_ns": {"0": 0.0}}, {"profile_sha256": "0" * 64}):
        broken = tmp_path / f"broken-{len(change)}-{next(iter(change))}.json"
        broken.write_text(json.dumps({**offsets, **change}), encoding="utf-8")
        with pytest.raises(ProfileError):
            events.load_offsets(broken, profile)


def test_replay_record_is_immutable_and_blocks_without_clock(raw, tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(example()), encoding="utf-8")
    record = replay(profile_path, raw, tmp_path / "run.json", trigger_source="1")
    assert record["hardware_contacted"] is False
    assert record["blocked_stages"] == []
    assert record["stages"]["efficiency"]["numerator"] == 3
    assert record["raw"]["sha256"] == record["stages"]["decode"]["raw_sha256"]
    with pytest.raises(ValueError, match="immutable"):
        replay(profile_path, raw, tmp_path / "run.json", window_ns=5.0)
    with pytest.raises(FileExistsError):
        daq.write_fixture(raw, RECORDS)

    no_clock = copy.deepcopy(example())
    no_clock["clock"] = {"state": "unknown"}
    no_clock_path = tmp_path / "no-clock.json"
    no_clock_path.write_text(json.dumps(no_clock), encoding="utf-8")
    blocked = replay(no_clock_path, raw, tmp_path / "blocked.json")
    assert blocked["blocked_stages"] == ["clock"]
    assert "events" not in blocked["stages"]


def test_lab_cli_profile_and_replay(raw, tmp_path, capsys):
    assert main(["lab", "profile", str(INTAKE)]) == 0
    assert json.loads(capsys.readouterr().out)["identification"] == "unidentified"
    output = tmp_path / "cli-run.json"
    args = ["lab", "replay", "--profile", str(EXAMPLE), "--raw", str(raw), "--output", str(output)]
    assert main(args) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == "heplab-lab-replay-run-v1"
    assert (
        main(
            [
                "lab",
                "replay",
                "--profile",
                str(INTAKE),
                "--raw",
                str(raw),
                "--output",
                str(tmp_path / "x.json"),
                "--trigger-source",
                "1",
            ]
        )
        == 0
    )
