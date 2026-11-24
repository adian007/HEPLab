"""DELPHES adapter: preserve absent measurements and require declared MC weights."""

from __future__ import annotations


def read(
    source,
    *,
    tree="Delphes",
    entry_start=0,
    entry_stop=None,
    source_id="",
    allow_unit_weights=False,
    include_truth=True,
    **_kwargs,
):
    """Yield schema-v1 normalized Awkward batches from native DELPHES rows."""
    import awkward as ak
    import numpy as np
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
            "X",
            "Y",
            "Z",
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
        if not include_truth:
            collections.remove("Particle")
        leaves = sorted(
            {
                key.rsplit("/", 1)[-1]
                for key in native_tree.keys()
                if "." in key.rsplit("/", 1)[-1]
                and key.rsplit("/", 1)[-1].split(".", 1)[0] in collections
                and key.rsplit(".", 1)[-1] in fields
            }
        )

        def native(arrays, name):
            if name in arrays.fields:
                return arrays[name]
            collection, field = name.split(".", 1)
            if collection in arrays.fields and field in arrays[collection].fields:
                return arrays[collection][field]
            return None

        def missing_like(ak, pt):
            index = ak.local_index(pt, axis=1)
            return ak.mask(index, ak.zeros_like(index, dtype=bool))

        def objects(ak, arrays, prefix, specifications):
            pt = native(arrays, f"{prefix}.PT")
            if pt is None:
                return ak.Array([None] * len(arrays))
            columns = {"pt": pt}
            for field, branch, default in specifications:
                values = native(arrays, f"{prefix}.{branch}") if branch else None
                if values is None:
                    values = (
                        ak.full_like(pt, default) if default is not None else missing_like(ak, pt)
                    )
                elif not bool(ak.all(ak.num(values, axis=1) == ak.num(pt, axis=1))):
                    raise ValueError(f"DELPHES jagged mismatch in {prefix}.{field}")
                columns[field] = values
            columns["object_id"] = ak.local_index(pt, axis=1)
            return ak.zip(columns, depth_limit=2)

        def singleton(ak, value):
            if value is None:
                return ak.Array([None] * count)
            try:
                lengths = ak.num(value, axis=1)
            except (TypeError, ValueError):
                return value
            if not bool(ak.all(lengths == 1)):
                raise ValueError("DELPHES weight/MET must have one value per event")
            return ak.firsts(value, axis=1)

        for arrays in native_tree.iterate(
            leaves,
            entry_start=entry_start,
            entry_stop=entry_stop,
            step_size=100_000,
            library="ak",
        ):
            count = len(arrays)
            weight = native(arrays, "Event.Weight")
            if weight is None:
                weight = native(arrays, "Weight.Weight")
            if weight is None and not allow_unit_weights:
                raise ValueError("DELPHES source lacks weight; explicitly declare unweighted input")
            if weight is None:
                weight_values = np.ones(count)
            else:
                weight_values = singleton(ak, weight)
            common = [("pt", "PT", None), ("eta", "Eta", None), ("phi", "Phi", None)]
            met_pt = singleton(ak, native(arrays, "MissingET.MET"))
            met_phi = singleton(ak, native(arrays, "MissingET.Phi"))
            info = ak.zip(
                {
                    "run": np.zeros(count, dtype=np.int64),
                    "luminosity_block": np.zeros(count, dtype=np.int64),
                    "event": np.arange(entry_start, entry_start + count, dtype=np.int64),
                    "source_id": np.full(count, source_id),
                    "source_entry": np.arange(entry_start, entry_start + count, dtype=np.int64),
                    "is_data": np.zeros(count, dtype=bool),
                    "weight": weight_values,
                },
                depth_limit=1,
            )
            yield ak.zip(
                {
                    "EventInfo": info,
                    "Muon": objects(
                        ak,
                        arrays,
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
                        ak,
                        arrays,
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
                            ("mass", "Mass", None),
                            ("px", "Px", None),
                            ("py", "Py", None),
                            ("pz", "Pz", None),
                            ("charge", "Charge", None),
                            ("x_mm", "X", None),
                            ("y_mm", "Y", None),
                            ("z_mm", "Z", None),
                        ],
                    ),
                    "Electron": objects(
                        ak,
                        arrays,
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
                        ak,
                        arrays,
                        "Photon",
                        common
                        + [
                            ("mass", None, 0.0),
                            ("iso", "IsolationVar", None),
                            ("has_pixel_seed", None, None),
                        ],
                    ),
                    "Jet": objects(
                        ak, arrays, "Jet", common + [("mass", "Mass", None), ("btag", "BTag", None)]
                    ),
                    "MET": ak.zip({"pt": met_pt, "phi": met_phi}, depth_limit=1),
                    "Definitions": ak.zip(
                        {
                            "muon_iso": np.full(count, "delphes_card_isolation"),
                            "muon_id": ak.Array([None] * count),
                            "photon_pixel_seed": ak.Array([None] * count),
                            "jet_btag": np.full(count, "delphes_card_BTag"),
                        },
                        depth_limit=1,
                    ),
                },
                depth_limit=1,
            )


def read_events(*args, **kwargs):
    """Compatibility adapter for consumers that require schema-v1 event dictionaries."""
    for chunk in read(*args, **kwargs):
        yield from chunk.to_list()
