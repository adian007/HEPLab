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
GENPART_BRANCHES = (
    "GenPart_pt",
    "GenPart_eta",
    "GenPart_phi",
    "GenPart_mass",
    "GenPart_pdgId",
    "GenPart_status",
    "GenPart_genPartIdxMother",
)


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


def normalize_chunk(arrays: Any, *, is_data: bool, source_id: str, entry_start: int):
    """Normalize one Awkward batch without constructing event/object dictionaries."""
    import awkward as ak
    import numpy as np

    fields = set(arrays.fields)
    count = len(arrays)

    def scalar(name, default=None):
        if name in fields:
            return arrays[name]
        if default is None:
            return ak.Array([None] * count)
        return np.full(count, default)

    def collection(prefix, specs):
        pt_name = f"{prefix}_pt"
        if pt_name not in fields:
            return ak.Array([None] * count)
        pt = arrays[pt_name]
        values = {"pt": pt}
        for field, native, default in specs:
            name = f"{prefix}_{native}"
            if name in fields:
                column = arrays[name]
                if not bool(ak.all(ak.num(column, axis=1) == ak.num(pt, axis=1))):
                    raise ValueError(f"{prefix}.{field} shape does not match pt")
            elif default is None:
                index = ak.local_index(pt, axis=1)
                column = ak.mask(index, ak.zeros_like(index, dtype=bool))
            else:
                column = ak.full_like(pt, default)
            values[field] = column
        values["object_id"] = ak.local_index(pt, axis=1)
        return ak.zip(values, depth_limit=2)

    triggers = sorted(name for name in fields if name.startswith("HLT_"))
    fired = (
        np.column_stack([ak.to_numpy(arrays[name]) for name in triggers]).astype(bool, copy=False)
        if triggers
        else np.empty((count, 0), dtype=bool)
    )
    trigger_names = np.broadcast_to(np.asarray(triggers, dtype=str), fired.shape)
    info = ak.zip(
        {
            "run": ak.values_astype(scalar("run"), np.int64),
            "luminosity_block": ak.values_astype(scalar("luminosityBlock"), np.int64),
            "event": ak.values_astype(scalar("event"), np.int64),
            "is_data": np.full(count, is_data),
            "weight": np.ones(count) if is_data else arrays["genWeight"],
            "source_id": np.full(count, source_id),
            "source_entry": np.arange(entry_start, entry_start + count, dtype=np.int64),
        },
        depth_limit=1,
    )
    common = [(key, key, None) for key in ("pt", "eta", "phi", "mass", "charge")]
    result = {
        "EventInfo": info,
        "Muon": collection(
            "Muon", common + [("iso", "pfRelIso04_all", None), ("quality_flags", "tightId", None)]
        ),
        "Electron": collection(
            "Electron",
            common + [("iso", "pfRelIso03_all", None), ("quality_flags", "cutBased", None)],
        ),
        "Photon": collection(
            "Photon",
            [(key, key, None) for key in ("pt", "eta", "phi", "mass")]
            + [("iso", "pfRelIso03_all", None), ("has_pixel_seed", "pixelSeed", None)],
        ),
        "Jet": collection(
            "Jet",
            [(key, key, None) for key in ("pt", "eta", "phi", "mass")]
            + [("btag", "btagDeepB", None)],
        ),
        "MET": ak.zip({"pt": scalar("MET_pt"), "phi": scalar("MET_phi")}, depth_limit=1),
        "Trigger": ak.zip(
            {
                "names": ak.Array(trigger_names),
                "fired": ak.Array(fired),
                "source": np.full(count, "recorded"),
            },
            depth_limit=1,
        ),
        "Definitions": ak.zip(
            {
                "muon_iso": np.full(count, "cms_pfRelIso04"),
                "muon_id": np.full(count, "cms_tightId"),
                "photon_pixel_seed": np.full(count, "cms_pixelSeed"),
                "jet_btag": np.full(count, "cms_DeepB"),
            },
            depth_limit=1,
        ),
    }
    if "GenPart_pt" in fields:
        result["GenParticle"] = collection(
            "GenPart",
            [
                (key, native, None)
                for key, native in (
                    ("pt", "pt"),
                    ("eta", "eta"),
                    ("phi", "phi"),
                    ("mass", "mass"),
                    ("pdg_id", "pdgId"),
                    ("status", "status"),
                    ("parent_idx", "genPartIdxMother"),
                )
            ],
        )
    return ak.zip(result, depth_limit=1)


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
            requested.update(name for name in GENPART_BRANCHES if name in available)
        index = entry_start
        for arrays in native.iterate(
            sorted(requested & available),
            entry_start=entry_start,
            entry_stop=entry_stop,
            step_size=100_000,
            library="ak",
        ):
            yield normalize_chunk(arrays, is_data=is_data, source_id=source_id, entry_start=index)
            index += len(arrays)


def read_events(*args, **kwargs):
    """Compatibility adapter for consumers that require schema-v1 event dictionaries."""
    for chunk in read(*args, **kwargs):
        yield from chunk.to_list()
