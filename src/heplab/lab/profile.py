"""Versioned laboratory device profiles in which unknown values stay unknown.

A profile records what has been measured or documented about a physical detector.
Reported or unknown quantities are kept for the record but can never be used as
simulation or decoding defaults; ``require`` raises instead of guessing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..io.provenance import config_hash

SCHEMA = "heplab-lab-device-profile-v1"
STATES = {"unknown", "reported", "documented", "measured"}
# Only these states carry a traceable source strong enough to drive computation.
USABLE_STATES = {"documented", "measured"}
LENGTH_CM = {"mm": 0.1, "cm": 1.0, "m": 100.0}
TIME_NS = {"ps": 1e-3, "ns": 1.0, "us": 1e3}
IDENTITY_QUANTITIES = ("device_type", "serial_number", "active_length", "active_width")


class UnknownQuantity(LookupError):
    """A computation asked for a quantity the profile does not establish."""


class ProfileError(ValueError):
    """The profile is structurally or semantically invalid."""


@dataclass(frozen=True)
class Quantity:
    name: str
    state: str
    value: object = None
    unit: str | None = None
    source: str | None = None

    @property
    def usable(self) -> bool:
        return self.state in USABLE_STATES


def _quantity(name: str, raw: dict) -> Quantity:
    state = raw.get("state")
    if state not in STATES:
        raise ProfileError(f"{name}: state must be one of {sorted(STATES)}")
    if state == "unknown":
        if set(raw) - {"state", "note"}:
            raise ProfileError(f"{name}: unknown quantities cannot carry values")
        return Quantity(name, state)
    if "value" not in raw:
        raise ProfileError(f"{name}: {state} quantity has no value")
    if not raw.get("source"):
        raise ProfileError(f"{name}: {state} quantity has no source")
    value, unit = raw["value"], raw.get("unit")
    numbers = value if isinstance(value, list) else [value]
    if unit in LENGTH_CM or unit in TIME_NS:
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in numbers):
            raise ProfileError(f"{name}: dimensional value must be numeric")
        if isinstance(value, list) and (len(value) != 2 or value[0] > value[1]):
            raise ProfileError(f"{name}: a range must be [low, high]")
    return Quantity(name, state, value, unit, raw["source"])


@dataclass(frozen=True)
class DeviceProfile:
    profile_id: str
    identification: str
    quantities: dict[str, Quantity]
    channels: dict[int, dict]
    clock: dict | None
    trigger_sources: dict[str, dict]
    control_permitted: bool
    digest: str

    def require(self, name: str) -> Quantity:
        quantity = self.quantities.get(name)
        if quantity is None or not quantity.usable:
            state = "absent" if quantity is None else quantity.state
            raise UnknownQuantity(f"{self.profile_id}: {name} is {state}, not established")
        return quantity

    def length_cm(self, name: str) -> float:
        quantity = self.require(name)
        if quantity.unit not in LENGTH_CM or isinstance(quantity.value, list):
            raise ProfileError(f"{name}: not a single length value")
        return float(quantity.value) * LENGTH_CM[quantity.unit]  # type: ignore[arg-type]

    def require_clock(self) -> dict:
        if self.clock is None:
            raise UnknownQuantity(f"{self.profile_id}: DAQ clock is not established")
        return self.clock

    def unknowns(self) -> list[str]:
        missing = [name for name, q in sorted(self.quantities.items()) if not q.usable]
        if not self.channels:
            missing.append("channel_map")
        if self.clock is None:
            missing.append("clock")
        return missing


def load_profile(path: str | Path) -> DeviceProfile:
    return parse_profile(json.loads(Path(path).read_text(encoding="utf-8")))


def parse_profile(raw: dict) -> DeviceProfile:
    if raw.get("schema") != SCHEMA:
        raise ProfileError(f"profile schema must be {SCHEMA}")
    ident = raw.get("identification", {})
    status = ident.get("status")
    if status not in {"unidentified", "identified"}:
        raise ProfileError("identification.status must be unidentified or identified")
    quantities = {name: _quantity(name, q) for name, q in raw.get("quantities", {}).items()}
    channels: dict[int, dict] = {}
    channel_map = raw.get("channel_map", {"state": "unknown"})
    if channel_map.get("state") != "unknown":
        if channel_map.get("state") not in USABLE_STATES or not channel_map.get("source"):
            raise ProfileError("channel_map must be unknown, or documented/measured with a source")
        for entry in channel_map.get("channels", []):
            number = entry["channel"]
            if not isinstance(number, int) or number < 0 or number in channels:
                raise ProfileError(f"invalid or duplicate channel {number!r}")
            channels[number] = dict(entry)
        if not channels:
            raise ProfileError("an established channel map has no channels")
    clock = None
    clock_raw = raw.get("clock", {"state": "unknown"})
    if clock_raw.get("state") != "unknown":
        if clock_raw.get("state") not in USABLE_STATES or not clock_raw.get("source"):
            raise ProfileError("clock must be unknown, or documented/measured with a source")
        tick, bits = clock_raw.get("tick_ns"), clock_raw.get("counter_bits")
        if not isinstance(tick, (int, float)) or tick <= 0:
            raise ProfileError("clock.tick_ns must be positive")
        if not isinstance(bits, int) or not 1 <= bits <= 63:
            raise ProfileError("clock.counter_bits must be an integer in [1, 63]")
        clock = {"tick_ns": float(tick), "counter_bits": bits, "source": clock_raw["source"]}
    triggers = raw.get("trigger_sources", {})
    for trigger_id, trigger in triggers.items():
        if not isinstance(trigger.get("independent"), bool) or not trigger.get("description"):
            raise ProfileError(f"trigger source {trigger_id} needs independent and description")
    control = raw.get("control", {"permitted": False})
    if control.get("permitted") and not (
        status == "identified" and control.get("operator") and control.get("approved_limits")
    ):
        raise ProfileError("control requires identification, a named operator and approved limits")
    profile = DeviceProfile(
        profile_id=str(raw.get("profile_id", "")),
        identification=status,
        quantities=quantities,
        channels=channels,
        clock=clock,
        trigger_sources=dict(triggers),
        control_permitted=bool(control.get("permitted")),
        digest=config_hash(raw),
    )
    if not profile.profile_id:
        raise ProfileError("profile_id is required")
    if status == "identified":
        missing = [n for n in IDENTITY_QUANTITIES if not quantities.get(n, Quantity(n, "")).usable]
        if not channels:
            missing.append("channel_map")
        if missing:
            raise ProfileError(f"identified profile lacks established {', '.join(missing)}")
    return profile


def profile_summary(profile: DeviceProfile) -> dict:
    return {
        "profile_id": profile.profile_id,
        "profile_sha256": profile.digest,
        "identification": profile.identification,
        "channels": len(profile.channels),
        "clock_established": profile.clock is not None,
        "control_permitted": profile.control_permitted,
        "not_established": profile.unknowns(),
    }
