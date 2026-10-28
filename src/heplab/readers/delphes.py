"""DELPHES adapter: preserve absent measurements and require declared MC weights."""

from __future__ import annotations

from itertools import chain


def read(
    source,
    *,
    tree="Delphes",
    entry_start=0,
    entry_stop=None,
    source_id="",
    allow_unit_weights=False,
    **_kwargs,
):
    import uproot

    with uproot.open(source) as root:
        native_tree = root[tree]
        # Read physical leaves only. ROOT bookkeeping/TRef branches are neither
        # event observables nor portable uproot inputs (real DELPHES uses split TClonesArray).
        fields = {
            "PT",
            "Eta",
            "Phi",
            "Charge",
            "IsolationVar",
            "Mass",
            "BTag",
            "MET",
            "Weight",
            "Number",
            "PID",
            "Status",
            "M1",
            "M2",
            "D1",
            "D2",
            "E",
            "Px",
            "Py",
            "Pz",
        }
        collections = {
            "Muon",
            "Electron",
            "Photon",
            "Jet",
            "MissingET",
            "Event",
            "Weight",
            "Particle",
        }
        leaves = sorted(
            {
                key.rsplit("/", 1)[-1]
                for key in native_tree.keys()
                if "." in key.rsplit("/", 1)[-1]
                and key.rsplit("/", 1)[-1].split(".", 1)[0] in collections
                and key.rsplit(".", 1)[-1] in fields
            }
        )
        arrays = chain.from_iterable(
            native_tree.iterate(
                leaves, entry_start=entry_start, entry_stop=entry_stop, step_size=256, library="ak"
            )
        )
        for index, row in enumerate(arrays, start=entry_start):

            def native(name, event_row=row):
                if name in event_row.fields:
                    value = event_row[name]
                else:
                    collection, field = name.split(".", 1)
                    if (
                        collection not in event_row.fields
                        or field not in event_row[collection].fields
                    ):
                        return None
                    value = event_row[collection][field]
                return value.to_list() if hasattr(value, "to_list") else value

            def objects(prefix, fields):
                pts = native(f"{prefix}.PT")
                if pts is None:
                    return None
                columns = {}
                for field, branch, default in fields:
                    values = native(f"{prefix}.{branch}") if branch else None
                    if values is None:
                        values = [default] * len(pts)
                    if not isinstance(values, list) or len(values) != len(pts):
                        raise ValueError(f"DELPHES jagged mismatch in {prefix}.{field}")
                    columns[field] = values
                return [
                    {key: values[i] for key, values in columns.items()} | {"object_id": i}
                    for i in range(len(pts))
                ]

            weight = native("Event.Weight")
            if weight is None:
                weight = native("Weight.Weight")
            if isinstance(weight, list):
                if len(weight) != 1:
                    raise ValueError("DELPHES weight must have one value per event")
                weight = weight[0]
            if weight is None and not allow_unit_weights:
                raise ValueError("DELPHES source lacks weight; explicitly declare unweighted input")
            common = [("pt", "PT", None), ("eta", "Eta", None), ("phi", "Phi", None)]
            met_pt = native("MissingET.MET")
            met_phi = native("MissingET.Phi")
            yield {
                "EventInfo": {
                    "run": 0,
                    "luminosity_block": 0,
                    "event": index,
                    "source_id": source_id,
                    "source_entry": index,
                    "is_data": False,
                    "weight": float(weight) if weight is not None else 1.0,
                },
                "Muon": objects(
                    "Muon",
                    common
                    + [
                        ("mass", None, 0.105658),
                        ("charge", "Charge", None),
                        ("iso", "IsolationVar", None),
                        ("quality_flags", None, None),
                    ],
                ),
                "Truth": objects(
                    "Particle",
                    common
                    + [
                        ("pdg_id", "PID", None),
                        ("status", "Status", None),
                        ("mother1", "M1", None),
                        ("mother2", "M2", None),
                        ("daughter1", "D1", None),
                        ("daughter2", "D2", None),
                        ("energy", "E", None),
                        ("px", "Px", None),
                        ("py", "Py", None),
                        ("pz", "Pz", None),
                    ],
                ),
                "Electron": objects(
                    "Electron",
                    common
                    + [
                        ("mass", None, 0.000511),
                        ("charge", "Charge", None),
                        ("iso", "IsolationVar", None),
                        ("quality_flags", None, None),
                    ],
                ),
                "Photon": objects(
                    "Photon",
                    common
                    + [
                        ("mass", None, 0.0),
                        ("iso", "IsolationVar", None),
                        ("has_pixel_seed", None, None),
                    ],
                ),
                "Jet": objects("Jet", common + [("mass", "Mass", None), ("btag", "BTag", None)]),
                "MET": {
                    "pt": met_pt[0] if met_pt else None,
                    "phi": met_phi[0] if met_phi else None,
                },
                "Definitions": {
                    "muon_iso": "delphes_card_isolation",
                    "muon_id": None,
                    "photon_pixel_seed": None,
                    "jet_btag": "delphes_card_BTag",
                },
            }
