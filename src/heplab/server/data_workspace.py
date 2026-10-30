"""Offline CMS NanoAOD workspace: bounded imports, cached events, immutable analyses.

Only registered samples or files explicitly uploaded into this project are read.
Data always pass the bundled 2016 luminosity mask; MC retains signed genWeight.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import math
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..io.certification import LumiMask
from ..io.provenance import config_hash, file_hash

MAX_FILE = 512 * 1024 * 1024
UPLOAD_IDLE_S = 120.0
MAX_EVENTS = 250_000
CERT = "Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.json"
BRANCHES = [
    "run",
    "luminosityBlock",
    "event",
    "Muon_pt",
    "Muon_eta",
    "Muon_phi",
    "Muon_mass",
    "Muon_charge",
    "Muon_tightId",
    "Muon_pfRelIso04_all",
    "HLT_Mu17_TrkIsoVVL_Mu8_TrkIsoVVL_DZ",
    "HLT_Mu17_TrkIsoVVL_TkMu8_TrkIsoVVL_DZ",
]


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    data_id: str = Field(default="cms-run2016g", pattern=r"^[A-Za-z0-9_-]{1,80}$")
    mc_id: str | None = Field(default="cms-dy-ul16", pattern=r"^[A-Za-z0-9_-]{1,80}$")
    min_pt: float = Field(default=15.0, ge=0, le=1000)
    leading_pt: float = Field(default=25.0, ge=0, le=1000)
    max_eta: float = Field(default=2.4, gt=0, le=5)
    max_iso: float = Field(default=0.15, gt=0, le=10)
    mass_low: float = Field(default=60.0, ge=0, le=1000)
    mass_high: float = Field(default=120.0, gt=0, le=1000)
    bins: int = Field(default=60, ge=10, le=200)
    require_trigger: bool = True
    require_tight: bool = True

    @model_validator(mode="after")
    def increasing(self):
        if self.mass_low >= self.mass_high:
            raise ValueError("upper mass must exceed lower mass")
        if self.leading_pt < self.min_pt:
            raise ValueError("leading pT must be at least the minimum muon pT")
        return self


ECAL_BARREL_RADIUS_M = 1.29
ECAL_ENDCAP_Z_M = 3.15


def electron_display_path(electron: dict) -> list[list[float]]:
    """Ideal 3.8 T helix from the IP, cut at the ECAL front face (display only)."""
    from ..physics.detector import trajectory
    from ..physics.reference import FourVector, TrackState

    state = TrackState(
        (0.0, 0.0, 0.0),
        FourVector.from_pt_eta_phi_mass(
            electron["pt"], electron["eta"], electron["phi"], 0.000510999
        ),
        electron["charge"],
        0.0,
    )
    points = []
    for point in trajectory(state, max_path=8.0, step=0.02)["points"]:
        if math.hypot(point[0], point[1]) > ECAL_BARREL_RADIUS_M or abs(point[2]) > ECAL_ENDCAP_Z_M:
            break
        points.append(point)
    return points


def sample_folder() -> Path:
    if os.environ.get("HEPLAB_CMS_SAMPLE_DIR"):
        return Path(os.environ["HEPLAB_CMS_SAMPLE_DIR"])
    bundled = Path(__file__).resolve().parents[1] / "data/cms-samples"
    return (
        bundled
        if bundled.is_dir()
        else Path(__file__).resolve().parents[3] / "artifacts/cms/measured"
    )


def certification_path(folder: Path) -> Path:
    bundled = folder / CERT
    packaged = Path(__file__).resolve().parents[1] / "data/certification" / CERT
    return (
        bundled
        if bundled.is_file()
        else packaged
        if packaged.is_file()
        else Path(__file__).resolve().parents[3] / "manifests/certification" / CERT
    )


def histogram(values, weights, edges):
    import numpy as np

    edges = np.asarray(edges, dtype=float)
    buckets = np.searchsorted(edges, values, side="right")
    size = len(edges) + 1
    counts = np.bincount(buckets, minlength=size)
    sumw = np.bincount(buckets, weights=weights, minlength=size)
    sumw2 = np.bincount(buckets, weights=weights**2, minlength=size)
    total = float(sumw.sum())
    fractions = covariance = None
    if total > 0:
        fractions = sumw / total
        jacobian = (np.eye(size) - fractions[:, None]) / total
        covariance = (jacobian * sumw2) @ jacobian.T
    return dict(
        edges=edges.tolist(),
        entries=counts.tolist(),
        sumw=sumw.tolist(),
        sumw2=sumw2.tolist(),
        fractions=None if fractions is None else fractions.tolist(),
        covariance=None if covariance is None else covariance.tolist(),
        total_sumw=total,
        total_sumw2=float(sumw2.sum()),
    )


def select(arrays, kind: str, mask: LumiMask, config: Selection):
    import awkward as ak
    import numpy as np

    count = len(arrays)
    weights = np.ones(count) if kind == "data" else ak.to_numpy(arrays["genWeight"]).astype(float)
    certified = np.ones(count, dtype=bool)
    if kind == "data":
        certified = np.array(
            [
                mask.accepts(int(run), int(lumi))
                for run, lumi in zip(arrays["run"], arrays["luminosityBlock"], strict=True)
            ]
        )
    trigger = ak.to_numpy(arrays[BRANCHES[-1]] | arrays[BRANCHES[-2]])
    muons = ak.zip(
        {
            key: arrays["Muon_" + field]
            for key, field in [
                ("pt", "pt"),
                ("eta", "eta"),
                ("phi", "phi"),
                ("mass", "mass"),
                ("charge", "charge"),
                ("tight", "tightId"),
                ("iso", "pfRelIso04_all"),
            ]
        }
    )
    accepted = (
        (muons.pt > config.min_pt)
        & (abs(muons.eta) < config.max_eta)
        & (muons.iso < config.max_iso)
    )
    if config.require_tight:
        accepted = accepted & muons.tight
    muons = muons[accepted]
    pairs = ak.combinations(muons, 2, fields=["a", "b"])
    pairs = pairs[
        (pairs.a.charge * pairs.b.charge < 0)
        & ((pairs.a.pt > config.leading_pt) | (pairs.b.pt > config.leading_pt))
    ]
    pairs = pairs[ak.argsort(pairs.a.pt + pairs.b.pt, ascending=False, stable=True)]
    candidate = ak.firsts(pairs)
    present = ak.to_numpy(~ak.is_none(candidate))

    def column(side, field):
        return ak.to_numpy(ak.fill_none(candidate[side][field], 0)).astype(float)

    apt, bpt = column("a", "pt"), column("b", "pt")
    aeta, beta = column("a", "eta"), column("b", "eta")
    aphi, bphi = column("a", "phi"), column("b", "phi")
    am, bm = column("a", "mass"), column("b", "mass")
    px, py = apt * np.cos(aphi) + bpt * np.cos(bphi), apt * np.sin(aphi) + bpt * np.sin(bphi)
    pz = apt * np.sinh(aeta) + bpt * np.sinh(beta)
    energy = np.sqrt(am**2 + (apt * np.cosh(aeta)) ** 2) + np.sqrt(
        bm**2 + (bpt * np.cosh(beta)) ** 2
    )
    mass = np.sqrt(np.maximum(0, energy**2 - px**2 - py**2 - pz**2))
    stages = [np.ones(count, dtype=bool), certified]
    stages.append(certified & trigger if config.require_trigger else certified.copy())
    stages.append(stages[-1] & ak.to_numpy(ak.num(muons) >= 2))
    stages.append(stages[-1] & present)
    stages.append(stages[-1] & (mass >= config.mass_low) & (mass < config.mass_high))
    selected = stages[-1]
    fields = dict(
        mass=mass[selected],
        leading_pt=np.maximum(apt, bpt)[selected],
        leading_eta=np.where(apt >= bpt, aeta, beta)[selected],
        pair_pt=np.hypot(px, py)[selected],
    )
    edges = dict(
        mass=np.linspace(config.mass_low, config.mass_high, config.bins + 1),
        leading_pt=np.linspace(0, 200, 41),
        leading_eta=np.linspace(-5, 5, 41),
        pair_pt=np.linspace(0, 200, 41),
    )
    labels = [
        "Input events",
        "Certified data / MC",
        "DZ trigger" if config.require_trigger else "Trigger off",
        "Two selected muons",
        "OS pair + leading pT",
        "Mass window",
    ]
    cutflow = [
        dict(
            stage=label,
            events=int(gate.sum()),
            sumw=float(weights[gate].sum()),
            sumw2=float((weights[gate] ** 2).sum()),
        )
        for label, gate in zip(labels, stages, strict=True)
    ]
    rows = [
        dict(
            entry=int(i),
            run=str(int(arrays["run"][i])),
            lumi=str(int(arrays["luminosityBlock"][i])),
            event=str(int(arrays["event"][i])),
            weight=float(weights[i]),
            mass_gev=float(mass[i]),
            leading_pt_gev=float(max(apt[i], bpt[i])),
            leading_eta=float(aeta[i] if apt[i] >= bpt[i] else beta[i]),
            pair_pt_gev=float(np.hypot(px[i], py[i])),
        )
        for i in np.flatnonzero(selected)
    ]
    return dict(
        events=count,
        selected_events=len(rows),
        cutflow=cutflow,
        histograms={
            key: histogram(values, weights[selected], edges[key]) for key, values in fields.items()
        },
    ), rows


class DataWorkspace:
    def __init__(self, root: Path):
        self.project = Path(root).resolve()
        self.root = self.project / "data-workspace"
        self.confined(self.root)
        self.folder = sample_folder()
        self.cache: dict[str, dict[str, Any]] = {}
        self.display_cache: dict[str, dict] = {}
        self.uploads: dict[str, dict[str, Any]] = {}
        self.reads = 0

    def confined(self, path):
        if not path.resolve().is_relative_to(self.project):
            raise ValueError("dataset workspace leaves the project")
        for part in (path, *path.parents):
            if part == self.project:
                break
            if part.is_symlink():
                raise ValueError("symbolic links are not followed")
        return path

    def descriptors(self):
        self.confined(self.root / "datasets")
        items = []
        for identity, name, kind, filename, metadata in [
            (
                "cms-run2016g",
                "CMS Run2016G · recorded data",
                "data",
                "run2016g-100k.root",
                "source.json",
            ),
            (
                "cms-dy-ul16",
                "CMS UL2016 Drell–Yan · full simulation",
                "mc",
                "dy-ul16-100k.root",
                "dy-source.json",
            ),
        ]:
            path, record = self.folder / filename, self.folder / metadata
            if path.is_file() and record.is_file():
                source = json.loads(record.read_text(encoding="utf-8"))
                items.append(
                    dict(
                        id=identity,
                        name=name,
                        kind=kind,
                        path=path,
                        source=source,
                        sha256=source["derived_file_sha256"],
                        # Display-only sidecar (tools/build_cms_display_projection.py).
                        display=self.folder / filename.replace(".root", "-display.root"),
                    )
                )
        for path in sorted((self.root / "datasets").glob("*.json")):
            if path.is_symlink():
                continue
            item = json.loads(path.read_text(encoding="utf-8"))
            if item.get("id") != path.stem or not path.stem.startswith("local-"):
                continue
            item["path"] = path.with_suffix(".root")
            items.append(item)
        return {item["id"]: item for item in items}

    def library(self):
        return [
            dict(
                id=item["id"],
                name=item["name"],
                kind=item["kind"],
                bytes=item["path"].stat().st_size,
                sha256=item["sha256"],
                loaded=item["id"] in self.cache,
                source=item["source"],
            )
            for item in self.descriptors().values()
            if item["path"].is_file()
        ]

    def load(self, dataset_id):
        import awkward as ak
        import numpy as np
        import uproot

        item = self.descriptors().get(dataset_id)
        if item is None:
            raise ValueError("unknown dataset; choose a library sample or import a ROOT file")
        path = item["path"]
        if path.is_symlink() or path.stat().st_size > MAX_FILE:
            raise ValueError("dataset must be a regular file no larger than 512 MiB")
        fingerprint = (path.stat().st_size, path.stat().st_mtime_ns)
        if dataset_id in self.cache and self.cache[dataset_id]["fingerprint"] == fingerprint:
            return dict(
                id=dataset_id,
                events=len(self.cache[dataset_id]["arrays"]),
                reused=True,
                root_reads=self.reads,
            )
        if file_hash(path) != item["sha256"]:
            self.cache.pop(dataset_id, None)
            raise ValueError("dataset checksum changed; import the changed file as a new dataset")
        names = BRANCHES + (["genWeight"] if item["kind"] == "mc" else [])
        with uproot.open(path) as file:
            if "Events" not in file:
                raise ValueError("this workspace requires CMS NanoAOD with an Events tree")
            tree = file["Events"]
            if item["kind"] == "data" and "genWeight" in tree.keys():
                raise ValueError("this file declares generator weights; import it as simulation")
            missing = set(names) - set(tree.keys())
            if missing:
                raise ValueError("missing required CMS branches: " + ", ".join(sorted(missing)))
            if not 1 <= tree.num_entries <= MAX_EVENTS:
                raise ValueError("import a projection containing 1–250,000 events")
            if (
                sum(getattr(tree[name], "uncompressed_bytes", 0) for name in names)
                > 256 * 1024 * 1024
            ):
                raise ValueError("selected branch data exceed the 256 MiB memory budget")
            arrays = tree.arrays(names, library="ak")
        muon_lengths = ak.to_numpy(ak.num(arrays["Muon_pt"]))
        if np.any(muon_lengths > 128):
            raise ValueError("muon multiplicity exceeds the per-event budget")
        for name in names:
            if name.startswith("Muon_"):
                if not np.array_equal(ak.to_numpy(ak.num(arrays[name])), muon_lengths):
                    raise ValueError("inconsistent muon branch lengths")
                values = ak.to_numpy(ak.flatten(arrays[name]))
            else:
                values = ak.to_numpy(arrays[name])
            if not np.isfinite(values).all():
                raise ValueError("dataset contains nonfinite measurements")
        for field in ("pt", "mass", "pfRelIso04_all"):
            if ak.any(arrays["Muon_" + field] < 0):
                raise ValueError("negative muon measurement")
        if ak.any(abs(arrays["Muon_eta"]) > 10) or ak.any(abs(arrays["Muon_charge"]) != 1):
            raise ValueError("invalid CMS muon charge or pseudorapidity")
        identities = []
        for name in ("run", "luminosityBlock", "event"):
            values = ak.to_numpy(arrays[name])
            if values.dtype.kind not in "iu" or np.any(values < 0):
                raise ValueError("event identities must be nonnegative integers")
            identities.append(values)
        if len(np.unique(np.rec.fromarrays(identities))) != len(arrays):
            raise ValueError("duplicate event identities in dataset")
        self.reads += 1
        if dataset_id not in self.cache and len(self.cache) >= 4:
            self.cache.pop(next(iter(self.cache)))
        self.cache[dataset_id] = dict(arrays=arrays, fingerprint=fingerprint, descriptor=item)
        return dict(id=dataset_id, events=len(arrays), reused=False, root_reads=self.reads)

    def analyze(self, config):
        import numpy as np

        cuts = Selection.model_validate(config)
        identifiers = [("data", cuts.data_id)] + ([("mc", cuts.mc_id)] if cuts.mc_id else [])
        populations, ledgers = {}, {}
        mask = LumiMask(certification_path(self.folder))
        for role, identity in identifiers:
            self.load(identity)
            entry = self.cache[identity]
            if entry["descriptor"]["kind"] != role:
                raise ValueError(f"select a {role} dataset for the {role} population")
            population, rows = select(entry["arrays"], role, mask, cuts)
            desc = entry["descriptor"]
            population["dataset"] = dict(
                id=identity, name=desc["name"], sha256=desc["sha256"], source=desc["source"]
            )
            populations[role], ledgers[role] = population, rows
        ratio: list[dict[str, float | None]] = []
        if "mc" in populations:
            data, mc = (populations[role]["histograms"]["mass"] for role in ("data", "mc"))
            for i in range(1, len(data["edges"])):
                if data["fractions"] is None or mc["fractions"] is None or mc["fractions"][i] <= 0:
                    ratio.append(dict(value=None, error=None))
                else:
                    a, b = data["fractions"][i], mc["fractions"][i]
                    variance = (
                        data["covariance"][i][i] / b**2 + a * a * mc["covariance"][i][i] / b**4
                    )
                    ratio.append(dict(value=a / b, error=float(np.sqrt(max(0, variance)))))
        identity = secrets.token_hex(12)
        report = dict(
            id=identity,
            schema="heplab-cms-analysis-v1",
            created_utc=datetime.now(UTC).isoformat(),
            config=cuts.model_dump(),
            config_sha256=config_hash(cuts.model_dump()),
            certification_sha256=mask.sha256,
            populations=populations,
            mass_ratio=ratio,
            root_reads=self.reads,
            pair_policy="highest scalar pT OS pair before mass cut",
            normalization=(
                "Each population normalized to its selected signed weight sum, including flow bins"
            ),
            uncertainties=(
                "Statistical only; normalized-bin covariance retained; independent data and MC"
            ),
            limitations=[
                "First-file projections are not a luminosity-representative sample",
                "No Rochester/efficiency corrections or pileup reweighting",
                "No physics-systematic or background-model uncertainty",
                "Recorded data always require Legacy2016 luminosity certification",
                "Local derived-file identity verified; full remote-source checksum not verified",
                "Shape agreement does not establish detector calibration",
            ],
        )
        directory = self.confined(self.root / "analyses" / identity)
        directory.mkdir(parents=True)
        for role, rows in ledgers.items():
            with (directory / f"{role}.csv").open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[
                        "entry",
                        "run",
                        "lumi",
                        "event",
                        "weight",
                        "mass_gev",
                        "leading_pt_gev",
                        "leading_eta",
                        "pair_pt_gev",
                    ],
                )
                writer.writeheader()
                writer.writerows(rows)
        (directory / "analysis.json").write_text(
            json.dumps(report, allow_nan=False), encoding="utf-8"
        )
        return report

    def event(self, analysis_id, index):
        from itertools import islice

        from .workbench import muon_display

        report = self.get(analysis_id)
        population = report["populations"]["data"]
        if type(index) is not int or not 0 <= index < population["selected_events"]:
            raise ValueError("selected event index out of range")
        identity = report["config"]["data_id"]
        self.load(identity)
        cached = self.cache[identity]
        if cached["descriptor"]["sha256"] != population["dataset"]["sha256"]:
            raise ValueError("saved analysis source identity changed")
        with (self.root / "analyses" / analysis_id / "data.csv").open(
            encoding="utf-8", newline=""
        ) as file:
            row = next(islice(csv.DictReader(file), index, index + 1))
        arrays = cached["arrays"]
        entry = int(row["entry"])
        for name, key in [("run", "run"), ("luminosityBlock", "lumi"), ("event", "event")]:
            if str(int(arrays[name][entry])) != row[key]:
                raise ValueError("saved event identity does not match source")
        muons = [
            dict(
                object_id=i,
                pt=float(pt),
                eta=float(arrays["Muon_eta"][entry][i]),
                phi=float(arrays["Muon_phi"][entry][i]),
                charge=int(arrays["Muon_charge"][entry][i]),
                iso=float(arrays["Muon_pfRelIso04_all"][entry][i]),
            )
            for i, pt in enumerate(arrays["Muon_pt"][entry])
            if float(pt) > 0
        ]
        display = muon_display(muons, index)
        display.update(
            mode="cms",
            analysis_id=analysis_id,
            events=population["selected_events"],
            config=report["config"],
            identity={key: row[key] for key in ["run", "lumi", "event", "entry"]},
            mass_gev=float(row["mass_gev"]),
            dataset=population["dataset"],
        )
        objects, unavailable = self.display_objects(identity, entry, display["identity"])
        if objects:
            for electron in objects["electrons"]:
                electron["points"] = electron_display_path(electron)
        display["objects"] = objects
        display["objects_unavailable"] = unavailable
        display["display"] = (
            "Recorded CMS muons (ideal 3.8 T helix from the IP) with reconstructed "
            "NanoAOD jets, electrons, photons and MET; towers are drawn from jet "
            "energy fractions, not calorimeter hits"
            if objects
            else "Recorded CMS muons · origin assumed at IP, ideal 3.8 T helix · "
            "predicted crossings, no measured hits, jets or calorimeter deposits"
        )
        return display

    def display_objects(self, dataset_id, entry, identity):
        """Reconstructed objects for one entry, joined from the display sidecar.

        Returns (objects, None) or (None, reason). The sidecar must declare the
        loaded base file's SHA-256 and carry the same run/lumi/event at ``entry``.
        """
        import uproot

        item = self.descriptors().get(dataset_id)
        path = item and item.get("display")
        if not path or not path.is_file() or path.is_symlink():
            return None, "no display sidecar for this dataset; muons only"
        record_path = path.with_suffix(".json")
        if not record_path.is_file():
            return None, "display sidecar has no source record"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        fingerprint = (path.stat().st_size, path.stat().st_mtime_ns)
        verified = self.display_cache.setdefault("verified", {})
        if verified.get(dataset_id) != fingerprint:
            if record.get("joins_sha256") != item["sha256"]:
                return None, "display sidecar was built for a different base file"
            if file_hash(path) != record.get("derived_file_sha256"):
                return None, "display sidecar checksum changed"
            verified[dataset_id] = fingerprint
        # Browsing steps through nearby entries: decode 2000-entry blocks once.
        blocks = self.display_cache.setdefault("blocks", {})
        start = entry - entry % 2000
        key = (dataset_id, fingerprint, start)
        if key not in blocks:
            with uproot.open(path) as file:
                tree = file["Events"]
                if not 0 <= entry < tree.num_entries:
                    return None, "display sidecar does not cover this entry"
                stop = min(start + 2000, tree.num_entries)
                if len(blocks) >= 8:
                    blocks.pop(next(iter(blocks)))
                blocks[key] = tree.arrays(entry_start=start, entry_stop=stop, library="ak")
        block = blocks[key]
        if entry - start >= len(block):
            return None, "display sidecar does not cover this entry"
        row = block[entry - start]
        if [str(int(row[k])) for k in ("run", "luminosityBlock", "event")] != [
            identity["run"],
            identity["lumi"],
            identity["event"],
        ]:
            return None, "display sidecar event identity does not match; refusing to join"

        def collection(name, fields, rename=None):
            values = [row[f"{name}_{field}"].tolist() for field in fields]
            out = []
            for index, entries in enumerate(zip(*values, strict=True)):
                item = {"index": index}
                for field, value in zip(fields, entries, strict=True):
                    item[(rename or {}).get(field, field)] = value
                out.append(item)
            return out

        jets = collection(
            "Jet",
            ["pt", "eta", "phi", "mass", "jetId", "puId", "btagDeepFlavB",
             "chEmEF", "neEmEF", "chHEF", "neHEF"],
            {"jetId": "jet_id", "puId": "pu_id", "btagDeepFlavB": "btag_deepflav_b"},
        )  # fmt: skip
        for jet in jets:
            # Energy fractions are reconstructed PF content, used only to split tower height.
            jet["em_fraction"] = jet.pop("chEmEF") + jet.pop("neEmEF")
            jet["hadronic_fraction"] = jet.pop("chHEF") + jet.pop("neHEF")
        cm = 0.01
        return {
            "jets": jets,
            "electrons": collection(
                "Electron",
                ["pt", "eta", "phi", "mass", "charge", "cutBased", "pfRelIso03_all", "dxy", "dz"],
                {"cutBased": "cut_based_id", "pfRelIso03_all": "iso"},
            ),
            "photons": collection(
                "Photon",
                ["pt", "eta", "phi", "cutBased", "pfRelIso03_all"],
                {"cutBased": "cut_based_id", "pfRelIso03_all": "iso"},
            ),
            "taus": collection(
                "Tau", ["pt", "eta", "phi", "charge", "decayMode"], {"decayMode": "decay_mode"}
            ),
            "isotracks": collection("IsoTrack", ["pt", "eta", "phi", "dz"]),
            "muon_quality": collection(
                "Muon",
                [
                    "dxy",
                    "dz",
                    "isGlobal",
                    "isTracker",
                    "isStandalone",
                    "nStations",
                    "nTrackerLayers",
                    "ptErr",
                ],
                {
                    "isGlobal": "is_global",
                    "isTracker": "is_tracker",
                    "isStandalone": "is_standalone",
                    "nStations": "stations",
                    "nTrackerLayers": "tracker_layers",
                    "ptErr": "pt_error",
                },
            ),  # fmt: skip
            "met": {
                "pt": float(row["MET_pt"]),
                "phi": float(row["MET_phi"]),
                "sum_et": float(row["MET_sumEt"]),
                "puppi_pt": float(row["PuppiMET_pt"]),
                "puppi_phi": float(row["PuppiMET_phi"]),
            },
            "vertex": {
                "position_m": [
                    float(row["PV_x"]) * cm,
                    float(row["PV_y"]) * cm,
                    float(row["PV_z"]) * cm,
                ],
                "vertices": int(row["PV_npvs"]),
                "good_vertices": int(row["PV_npvsGood"]),
            },
            "units": "GeV, rad; vertex in metres; dxy/dz in cm as stored by NanoAOD",
            "source": {
                "file": path.name,
                "sha256": record["derived_file_sha256"],
                "record": record.get("record"),
                "scope": record.get("purpose"),
            },
        }, None

    def analyses(self, offset=0):
        if type(offset) is not int or offset < 0:
            raise ValueError("invalid analysis offset")
        directory = self.confined(self.root / "analyses")
        items = []
        for folder in directory.glob("*"):
            try:
                report = self.get(folder.name)
                items.append(
                    dict(
                        id=report["id"],
                        created_utc=report["created_utc"],
                        config=report["config"],
                        populations={
                            role: dict(
                                name=p["dataset"]["name"], selected_events=p["selected_events"]
                            )
                            for role, p in report["populations"].items()
                        },
                    )
                )
            except (ValueError, OSError, KeyError, TypeError):
                continue
        items.sort(key=lambda item: (item["created_utc"], item["id"]), reverse=True)
        return dict(
            items=items[offset : offset + 25],
            total=len(items),
            next_offset=min(offset + 25, len(items)),
        )

    def get(self, analysis_id):
        if len(analysis_id) != 24 or any(c not in "0123456789abcdef" for c in analysis_id):
            raise ValueError("invalid analysis ID")
        directory = self.confined(self.root / "analyses" / analysis_id)
        path = directory / "analysis.json"
        if directory.is_symlink() or path.is_symlink():
            raise ValueError("symbolic links are not followed")
        return json.loads(path.read_text(encoding="utf-8"))

    def rows(self, analysis_id, role, offset=0):
        report = self.get(analysis_id)
        if role not in {"data", "mc"} or role not in report["populations"]:
            raise ValueError("population unavailable")
        if type(offset) is not int or not 0 <= offset <= MAX_EVENTS:
            raise ValueError("invalid row offset")
        with (self.root / "analyses" / analysis_id / f"{role}.csv").open(
            encoding="utf-8", newline=""
        ) as file:
            rows = list(csv.reader(file))
        buffer = io.StringIO(newline="")
        csv.writer(buffer).writerows(
            ([rows[0]] if offset == 0 else []) + rows[offset + 1 : offset + 1001]
        )
        return dict(
            text=buffer.getvalue(),
            next_offset=min(offset + 1000, len(rows) - 1),
            total=len(rows) - 1,
        )

    def import_begin(self, config):
        if set(config) != {"name", "kind", "size"} or config["kind"] not in {"data", "mc"}:
            raise ValueError("import requires name, kind and size")
        if not isinstance(config["name"], str) or not 1 <= len(config["name"]) <= 120:
            raise ValueError("provide a short dataset name")
        if type(config["size"]) is not int or not 1 <= config["size"] <= MAX_FILE:
            raise ValueError("ROOT files must be no larger than 512 MiB")
        # A closed or reloaded tab never finishes its upload; let it go stale.
        for stale in [
            key
            for key, upload in self.uploads.items()
            if time.monotonic() - upload["touched"] > UPLOAD_IDLE_S
        ]:
            self.import_abort(stale)
        if self.uploads:
            raise ValueError("finish or cancel the active import first")
        identity = secrets.token_hex(12)
        folder = self.confined(self.root / "imports")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (identity + ".part")
        path.touch(exist_ok=False)
        self.uploads[identity] = dict(config=config, path=path, offset=0, touched=time.monotonic())
        return {"id": identity}

    def import_chunk(self, config):
        if set(config) != {"id", "offset", "base64"}:
            raise ValueError("invalid upload chunk")
        if not isinstance(config["id"], str):
            raise ValueError("invalid upload id")
        upload = self.uploads[config["id"]]
        if type(config["offset"]) is not int or config["offset"] != upload["offset"]:
            raise ValueError("out-of-order upload")
        if not isinstance(config["base64"], str) or len(config["base64"]) > 44000:
            raise ValueError("upload chunk too large")
        data = base64.b64decode(config["base64"], validate=True)
        if not 1 <= len(data) <= 32768 or upload["offset"] + len(data) > upload["config"]["size"]:
            raise ValueError("upload exceeds declared size")
        with upload["path"].open("ab") as file:
            file.write(data)
        upload["offset"] += len(data)
        upload["touched"] = time.monotonic()
        return {"bytes": upload["offset"]}

    def import_finish(self, upload_id):
        upload = self.uploads[upload_id]
        if upload["offset"] != upload["config"]["size"]:
            raise ValueError("incomplete upload")
        checksum = file_hash(upload["path"])
        identity = "local-" + checksum[:24] + "-" + upload["config"]["kind"]
        folder = self.confined(self.root / "datasets")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (identity + ".root")
        meta = folder / (identity + ".json")
        if meta.exists():
            self.import_abort(upload_id)
            self.load(identity)
            return {"id": identity}
        upload["path"].replace(path)
        item = dict(
            id=identity,
            name=upload["config"]["name"],
            kind=upload["config"]["kind"],
            sha256=checksum,
            source={
                "integrity": "local import; original source provenance not declared",
                "derived_file_sha256": checksum,
            },
        )
        meta.write_text(json.dumps(item), encoding="utf-8")
        try:
            self.load(identity)
        except Exception:
            self.cache.pop(identity, None)
            path.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
            self.uploads.pop(upload_id)
            raise
        self.uploads.pop(upload_id)
        return {"id": identity}

    def import_abort(self, upload_id):
        upload = self.uploads.pop(upload_id, None)
        if upload:
            upload["path"].unlink(missing_ok=True)
        return {"cancelled": True}

    def close(self):
        for identity in list(self.uploads):
            self.import_abort(identity)


def operation_handlers(root: Path, closers=None):
    workspace = DataWorkspace(root)
    if closers is not None:
        closers.append(workspace.close)
    lock = threading.RLock()

    def locked(call):
        def handler(**args):
            with lock:
                return call(**args)

        return handler

    return {
        "data." + key: locked(call)
        for key, call in {
            "library": workspace.library,
            "analyses": workspace.analyses,
            "event": workspace.event,
            "load": workspace.load,
            "analyze": workspace.analyze,
            "get": workspace.get,
            "rows": workspace.rows,
            "import_begin": workspace.import_begin,
            "import_chunk": workspace.import_chunk,
            "import_finish": workspace.import_finish,
            "import_abort": workspace.import_abort,
        }.items()
    }
