"""NanoAOD normalization with explicit absence, shape checks and source identity."""

from __future__ import annotations

from typing import Any

READER_VERSION = "nanoaod-2"
BRANCHES = (
    "run",
    "luminosityBlock",
    "event",
    "Muon_pt",
    "Muon_eta",
    "Muon_phi",
    "Muon_mass",
    "Muon_charge",
    "Muon_pfRelIso04_all",
    "Muon_tightId",
    "Electron_pt",
    "Electron_eta",
    "Electron_phi",
    "Electron_mass",
    "Electron_charge",
    "Electron_pfRelIso03_all",
    "Electron_cutBased",
    "Photon_pt",
    "Photon_eta",
    "Photon_phi",
    "Photon_mass",
    "Photon_pfRelIso03_all",
    "Photon_pixelSeed",
    "Jet_pt",
    "Jet_eta",
    "Jet_phi",
    "Jet_mass",
    "Jet_btagDeepB",
    "MET_pt",
    "MET_phi",
)
REQUIRED = ("run", "luminosityBlock", "event", "Muon_pt", "Muon_eta", "Muon_phi", "Muon_charge")


def _value(entry, name, default=None):
    if name not in entry.fields:
        return default
    value = entry[name]
    if hasattr(value, "to_list"):
        return value.to_list()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _collection(entry, prefix, fields):
    pt = _value(entry, f"{prefix}_pt")
    if pt is None:
        return None
    if not isinstance(pt, list):
        raise ValueError(f"{prefix}_pt must be jagged")
    columns = {}
    for field, native, default in fields:
        values = _value(entry, f"{prefix}_{native}", [default] * len(pt))
        if not isinstance(values, list) or len(values) != len(pt):
            raise ValueError(f"{prefix}.{field} shape does not match pt")
        columns[field] = values
    return [
        {field: values[i] for field, values in columns.items()} | {"object_id": i}
        for i in range(len(pt))
    ]


def normalize_entry(entry: Any, is_data: bool = True) -> dict:
    for name in REQUIRED:
        if name not in entry.fields:
            raise ValueError(f"missing required NanoAOD branch {name}")
    if not is_data and "genWeight" not in entry.fields:
        raise ValueError("simulation NanoAOD requires generator weights")
    fields = [(k, k, None) for k in ("pt", "eta", "phi", "mass", "charge")]
    muons = _collection(
        entry,
        "Muon",
        fields + [("iso", "pfRelIso04_all", None), ("quality_flags", "tightId", None)],
    )
    electrons = _collection(
        entry,
        "Electron",
        fields + [("iso", "pfRelIso03_all", None), ("quality_flags", "cutBased", None)],
    )
    photons = _collection(
        entry,
        "Photon",
        [(k, k, None) for k in ("pt", "eta", "phi", "mass")]
        + [("iso", "pfRelIso03_all", None), ("has_pixel_seed", "pixelSeed", None)],
    )
    jets = _collection(
        entry,
        "Jet",
        [(k, k, None) for k in ("pt", "eta", "phi", "mass")] + [("btag", "btagDeepB", None)],
    )
    triggers = sorted(name for name in entry.fields if name.startswith("HLT_"))
    result = {
        "EventInfo": {
            "run": int(entry["run"]),
            "luminosity_block": int(entry["luminosityBlock"]),
            "event": int(entry["event"]),
            "is_data": is_data,
            "weight": 1.0 if is_data else float(entry["genWeight"]),
        },
        "Muon": muons,
        "Electron": electrons,
        "Photon": photons,
        "Jet": jets,
        "MET": {"pt": _value(entry, "MET_pt"), "phi": _value(entry, "MET_phi")},
        "Trigger": {
            "names": triggers,
            "fired": [bool(entry[name]) for name in triggers],
            "source": "recorded",
        },
        "Definitions": {
            "muon_iso": "cms_pfRelIso04",
            "muon_id": "cms_tightId",
            "photon_pixel_seed": "cms_pixelSeed",
            "jet_btag": "cms_DeepB",
        },
    }
    if "GenPart_pt" in entry.fields:
        truth = _collection(
            entry,
            "GenPart",
            [(k, k, None) for k in ("pt", "eta", "phi", "mass")]
            + [
                ("pdg_id", "pdgId", None),
                ("status", "status", None),
                ("parent_idx", "genPartIdxMother", None),
            ],
        )
        result["GenParticle"] = truth
    return result


def read(
    source: Any,
    *,
    tree: str = "Events",
    entry_start: int = 0,
    entry_stop: int | None = None,
    is_data: bool = True,
    branches: list[str] | None = None,
    source_id: str = "",
):
    import uproot

    with uproot.open(source) as root_file:
        if tree not in root_file:
            raise ValueError(f"NanoAOD tree {tree!r} not found")
        native = root_file[tree]
        available = set(native.keys())
        missing = set(REQUIRED) - available
        if missing:
            raise ValueError(f"missing required branches: {sorted(missing)}")
        requested = set(branches or BRANCHES) | set(REQUIRED)
        requested.update(name for name in available if name.startswith("HLT_"))
        if is_data and "genWeight" in available:
            raise ValueError("source carries genWeight (simulation); read it with --simulation")
        if not is_data:
            if "genWeight" not in available:
                raise ValueError("simulation source has no genWeight")
            requested.add("genWeight")
            requested.update(name for name in available if name.startswith("GenPart_"))
        index = entry_start
        for arrays in native.iterate(
            sorted(requested & available),
            entry_start=entry_start,
            entry_stop=entry_stop,
            step_size=100_000,
            library="ak",
        ):
            for entry in arrays:
                event = normalize_entry(entry, is_data=is_data)
                event["EventInfo"].update(source_id=source_id, source_entry=index)
                index += 1
                yield event
