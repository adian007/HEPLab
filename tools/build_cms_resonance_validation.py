"""Build/rebuild the frozen low-mass resonance fit report from CMS NanoAOD."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import urllib.parse
import zlib
from pathlib import Path
from urllib.request import Request, urlopen

import awkward as ak
import numpy as np
import scipy
import uproot
import yaml

from heplab.physics.cms_mass_calibration import (
    bootstrap_template,
    fit_template,
    heldout_closure,
)
from heplab.physics.cms_resonance_validation import (
    EVENT_SPLIT_ALGORITHM,
    RESONANCES,
    evaluate_reference,
    event_split,
    fit_peak,
    select_candidate_index,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    "https://opendata.cern.ch/eos/opendata/cms/Run2016G/DoubleMuon/NANOAOD/"
    "UL2016_MiniAODv2_NanoAODv9-v2/2430000/05DD095C-F6C3-9A4F-9FB3-348A5A6403D5.root"
)
DEFAULT_ENTRY_START = 100_000
DEFAULT_ENTRY_COUNT = 200_000
Z_BOOTSTRAP_REPLICATES = 20
ETA_BINS = ((0.0, 0.9), (0.9, 1.7), (1.7, 2.4))
TRIGGERS = {
    "jpsi": [
        "HLT_DoubleMu4_3_Jpsi_Displaced",
        "HLT_DoubleMu4_JpsiTrk_Displaced",
        "HLT_Mu7p5_L2Mu2_Jpsi",
        "HLT_Mu7p5_Track2_Jpsi",
        "HLT_Mu7p5_Track3p5_Jpsi",
        "HLT_Mu7p5_Track7_Jpsi",
        "HLT_Dimuon20_Jpsi",
        "HLT_Dimuon0er16_Jpsi_NoVertexing",
        "HLT_Dimuon0er16_Jpsi_NoOS_NoVertexing",
        "HLT_Dimuon6_Jpsi_NoVertexing",
    ],
    "upsilon": [
        "HLT_Mu7p5_L2Mu2_Upsilon",
        "HLT_Mu7p5_Track2_Upsilon",
        "HLT_Mu7p5_Track3p5_Upsilon",
        "HLT_Mu7p5_Track7_Upsilon",
        "HLT_Dimuon13_Upsilon",
        "HLT_Dimuon0_Upsilon_Muon",
    ],
}
MUON_BRANCHES = [
    "Muon_pt",
    "Muon_eta",
    "Muon_phi",
    "Muon_mass",
    "Muon_charge",
]
CERTIFICATION = (
    ROOT / "manifests/certification/Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.json"
)
DATASET_MANIFEST = ROOT / "manifests/datasets/run2016g_doublemuon.yaml"


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_pairs(source: str | Path, entry_start: int, entry_stop: int) -> tuple[list[dict], dict]:
    """Select one trigger-eligible pair per event using scalar pT sum only.

    The event range defaults to entries after the historical target-selected
    sample. A deterministic event-ID hash creates training and held-out
    partitions before any mass fit is evaluated.
    """
    if (
        type(entry_start) is not int
        or type(entry_stop) is not int
        or not 0 <= entry_start < entry_stop
    ):
        raise ValueError("entry range must be a nonempty nonnegative half-open interval")
    branches = ["run", "luminosityBlock", "event", *MUON_BRANCHES]
    branches += [branch for names in TRIGGERS.values() for branch in names]
    tree = uproot.open(source, timeout=60)["Events"]
    available = set(tree.keys())
    missing = set(branches) - available
    if missing:
        raise ValueError(f"NanoAOD source is missing branches: {sorted(missing)}")
    arrays = tree.arrays(
        branches,
        entry_start=min(entry_start, tree.num_entries),
        entry_stop=min(entry_stop, tree.num_entries),
        library="ak",
    )
    certified_lumis = json.loads(CERTIFICATION.read_text(encoding="utf8"))
    certified = np.asarray(
        [
            any(low <= lumi <= high for low, high in certified_lumis.get(str(int(run)), []))
            for run, lumi in zip(
                ak.to_list(arrays.run), ak.to_list(arrays.luminosityBlock), strict=True
            )
        ],
        dtype=np.bool_,
    )
    muons = ak.zip(
        {
            "pt": arrays.Muon_pt,
            "eta": arrays.Muon_eta,
            "phi": arrays.Muon_phi,
            "mass": arrays.Muon_mass,
            "charge": arrays.Muon_charge,
        }
    )
    pairs = ak.combinations(muons, 2, fields=["first", "second"])

    def four_vector(muon):
        return (
            np.sqrt(muon.mass**2 + (muon.pt * np.cosh(muon.eta)) ** 2),
            muon.pt * np.cos(muon.phi),
            muon.pt * np.sin(muon.phi),
            muon.pt * np.sinh(muon.eta),
        )

    first = four_vector(pairs.first)
    second = four_vector(pairs.second)
    mass = np.sqrt(
        np.maximum(
            0,
            (first[0] + second[0]) ** 2
            - (first[1] + second[1]) ** 2
            - (first[2] + second[2]) ** 2
            - (first[3] + second[3]) ** 2,
        )
    )
    certified_pairs = ak.broadcast_arrays(ak.Array(certified), mass)[0]
    quality = certified_pairs & (
        (pairs.first.charge * pairs.second.charge < 0)
        & (pairs.first.pt >= 2.0)
        & (pairs.second.pt >= 2.0)
        & (abs(pairs.first.eta) < 2.4)
        & (abs(pairs.second.eta) < 2.4)
    )
    fired = {}
    for population, names in TRIGGERS.items():
        accepted = ak.Array(np.zeros(len(arrays), dtype=np.bool_))
        for name in names:
            accepted = accepted | arrays[name]
        fired[population] = accepted

    runs = ak.to_list(arrays.run)
    lumis = ak.to_list(arrays.luminosityBlock)
    events = ak.to_list(arrays.event)
    rows = []
    event_count = {
        "entries_read": len(arrays),
        "entry_start": min(entry_start, tree.num_entries),
        "entry_stop": min(entry_stop, tree.num_entries),
        "certified_events": int(certified.sum()),
        "candidate_events": {},
    }
    split_counts = {population: {"training": 0, "heldout": 0} for population in fired}
    for population, resonance_names in (
        ("jpsi", ("jpsi",)),
        ("upsilon", ("upsilon_1s", "upsilon_2s", "upsilon_3s")),
    ):
        event_mask = ak.broadcast_arrays(fired[population], mass)[0]
        mask = quality & event_mask
        values = ak.to_list(mass[mask])
        eta1s = ak.to_list(pairs.first.eta[mask])
        eta2s = ak.to_list(pairs.second.eta[mask])
        pt1s = ak.to_list(pairs.first.pt[mask])
        pt2s = ak.to_list(pairs.second.pt[mask])
        population_rows = 0
        for index, (masses, eta1, eta2, pt1, pt2) in enumerate(
            zip(values, eta1s, eta2s, pt1s, pt2s, strict=True)
        ):
            p1, p2 = list(map(float, pt1)), list(map(float, pt2))
            candidate = select_candidate_index(zip(p1, p2, strict=True))
            if candidate is None:
                continue
            split = event_split(int(runs[index]), int(lumis[index]), int(events[index]))
            split_counts[population][split] += 1
            row = {
                "run": int(runs[index]),
                "luminosity_block": int(lumis[index]),
                "event": int(events[index]),
                "split": split,
                "selection_population": population,
                "candidate_pair_index": candidate,
                "mass_gev": float(masses[candidate]),
                "muon_pt_gev": [p1[candidate], p2[candidate]],
                "muon_abs_eta": [abs(float(eta1[candidate])), abs(float(eta2[candidate]))],
            }
            rows.extend(row | {"resonance": name} for name in resonance_names)
            population_rows += 1
        event_count["candidate_events"][population] = population_rows
    event_count["split_counts"] = split_counts
    return rows, event_count


def git_revision() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_dirty() -> bool | None:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        )
        return bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None


def _stable_result_value(value):
    """Quantize floating outputs before hashing for cross-platform CI parity."""
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_stable_result_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _stable_result_value(item) for key, item in value.items()}
    return value


def verify_source(source: str | Path, declared: dict) -> dict:
    """Validate the full NanoAOD file using its declared size and Adler-32."""
    expected_size = int(declared["source_size_bytes"])
    expected = str(declared["declared_adler32"]).lower()
    if isinstance(source, str) and urllib.parse.urlparse(source).scheme in {"http", "https"}:
        request = Request(str(source), method="HEAD", headers={"Want-Digest": "adler32"})
        with urlopen(request, timeout=45) as response:
            content_length = response.headers.get("Content-Length")
            actual_size = int(content_length) if content_length else expected_size
            digest = response.headers.get("Digest", "")
        if actual_size != expected_size:
            raise ValueError("CMS source file size differs from the frozen manifest")
        observed = next(
            (
                value.strip().strip('"').lower()
                for part in digest.split(",")
                for key, separator, value in [part.strip().partition("=")]
                if separator and key.lower().replace("-", "") == "adler32"
            ),
            None,
        )
        if observed is None:
            raise ValueError("CMS source did not provide a full-file Adler-32 digest")
        method = "CERN OpenData HTTP Want-Digest"
    else:
        checksum = 1
        size = 0
        with Path(source).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum = zlib.adler32(block, checksum)
                size += len(block)
        observed = f"{checksum & 0xFFFFFFFF:08x}"
        actual_size = size
        method = "local full-file bytes"
    if actual_size != expected_size or observed != expected:
        raise ValueError(
            f"CMS source integrity mismatch: expected {expected_size} bytes/{expected}, "
            f"observed {actual_size} bytes/{observed}"
        )
    return {"algorithm": "adler32", "value": observed, "verified": True, "method": method}


def report_from_rows(rows: list[dict], source_provenance: dict) -> dict:
    reference_path = ROOT / "src/heplab/data/reference/cms-resonance-validation.json"
    reference = json.loads(reference_path.read_text(encoding="utf8"))
    result: dict = {
        "schema": "heplab-cms-data-resonance-validation-v2",
        "status": "data_regression_gate",
        "validation_level": "named_reference_data_regression",
        "source": source_provenance,
        "selection": {
            "event": (
                f"entries [{source_provenance['entry_start']}, {source_provenance['entry_stop']}) "
                "from one Run2016G "
                "DoubleMuon NanoAOD file; certified run/lumi subset"
            ),
            "muons": "opposite charge; pT >= 2 GeV; |eta| < 2.4",
            "trigger": (
                "OR of recorded low-mass J/psi or Upsilon trigger paths "
                "listed in the source manifest"
            ),
            "candidate": (
                "one opposite-charge pair per event, maximizing scalar pT sum; "
                "stable pair-order tie break; mass is not used"
            ),
            "split": {
                "algorithm": EVENT_SPLIT_ALGORITHM,
                "key": "run:luminosityBlock:event",
                "heldout_fraction": 0.2,
                "selection_and_split_precede_mass_fit": True,
            },
        },
        "fits": {},
        "limits": [
            "Held-out events are disjoint from training; they come from one file and run period, "
            "so they do not constitute an independent dataset",
            "Candidate selection is mass-independent, but trigger populations and offline cuts "
            "still define acceptance",
            "No trigger-object matching, acceptance correction, or per-muon momentum correction",
            "The resonance peak fit is a data spectrum regression, not a "
            "detector-response calibration",
            "Eta-bin comparisons are broad cross-era envelopes digitized from the cited CMS plot",
        ],
    }
    splits = {row.get("split") for row in rows}
    if not splits <= {"training", "heldout"} or not {"training", "heldout"} <= splits:
        raise ValueError("v2 candidate rows require both training and held-out event splits")
    event_keys = {}
    for row in rows:
        key = (row["resonance"], row["run"], row["luminosity_block"], row["event"])
        prior = event_keys.setdefault(key, row["split"])
        if prior != row["split"]:
            raise ValueError("one event appears in both training and held-out populations")
    masses = {
        name: {
            split: [
                row["mass_gev"]
                for row in rows
                if row["resonance"] == name and row["split"] == split
            ]
            for split in ("training", "heldout")
        }
        for name in RESONANCES
    }
    for name, config in RESONANCES.items():
        training_fit = fit_peak(masses[name]["training"], tuple(config["window_gev"]))
        heldout_fit = fit_peak(masses[name]["heldout"], tuple(config["window_gev"]))
        gate = evaluate_reference(heldout_fit, reference["resonance_masses_gev"][name])
        result["fits"][name] = {
            "entries": {split: len(population) for split, population in masses[name].items()},
            "training_fit": training_fit,
            "heldout_fit": heldout_fit,
            "heldout_reference_gate": gate,
        }

    # Z uses its independent high-mass data/MC template and held-out closure.
    z_fixture_path = ROOT / "src/heplab/data/reference/cms-z-template-candidates.json"
    z_fixture = json.loads(z_fixture_path.read_text(encoding="utf8"))
    fixture_hash = z_fixture.pop("sha256")
    actual_hash = hashlib.sha256(
        json.dumps(z_fixture, sort_keys=True, separators=(",", ":")).encode("utf8")
    ).hexdigest()
    if fixture_hash != actual_hash:
        raise ValueError("frozen Z template candidates do not match their SHA-256")
    z_fixture["sha256"] = fixture_hash
    z_input = json.loads(
        (ROOT / "src/heplab/data/reference/cms-measured-validation.json").read_text(encoding="utf8")
    )
    z_reference_report = json.loads(
        (ROOT / "src/heplab/data/reference/cms-mass-calibration.json").read_text(encoding="utf8")
    )
    if z_fixture["data_source"]["selected_pairs_sha256"] != z_input["selected_pairs_sha256"]:
        raise ValueError("frozen Z data candidates do not match the selected-pair provenance")
    if z_fixture["mc_source"] != z_reference_report["mc_source"]:
        raise ValueError("frozen Z MC candidates do not match the MC source provenance")
    z_data = z_fixture["data_masses_gev"]
    z_mc = z_fixture["mc_masses_gev"]
    z_edges = z_fixture["fit_edges_gev"]
    z_fit = fit_template(z_data[0], z_mc[0], z_edges)
    z_bootstrap = bootstrap_template(z_data[0], z_mc[0], z_edges, replicates=Z_BOOTSTRAP_REPLICATES)
    z_heldout = heldout_closure(
        z_data[1], z_mc[1], z_edges, z_fit["parameters"], z_bootstrap["parameters"]
    )
    z_raw_fit = fit_peak(z_data[0] + z_data[1], (75.0, 105.0))
    result["z_dimuon"] = {
        "data_pairs": list(map(len, z_data)),
        "raw_data_spectrum_fit": z_raw_fit,
        "template_fit": z_fit,
        "bootstrap": {
            "seed": z_bootstrap["seed"],
            "requested": z_bootstrap["requested"],
            "successful": z_bootstrap["successful"],
            "intervals_95_percent": z_bootstrap["intervals_95_percent"],
        },
        "heldout_template_closure": z_heldout,
        "published_reference": reference["sources"]["z_mass"],
        "published_mass_gev": reference["resonance_masses_gev"]["z"]["mass"],
        "passed": bool(z_heldout["passed"]),
        "interpretation": (
            "The gate is the frozen held-out data/MC shape closure. "
            "The raw peak fit is diagnostic: "
            "it includes FSR and uses no Rochester or precision-scale correction, so it is not "
            "directly compared to the published precision Z mass."
        ),
    }

    jpsi_rows = [row for row in rows if row["resonance"] == "jpsi" and row["split"] == "heldout"]
    eta_results = []
    eta_refs = reference["jpsi_relative_mass_resolution_by_abs_eta"]
    for (low, high), eta_ref in zip(ETA_BINS, eta_refs, strict=True):
        values = [
            row["mass_gev"] for row in jpsi_rows for eta in row["muon_abs_eta"] if low <= eta < high
        ]
        fit = fit_peak(values, tuple(RESONANCES["jpsi"]["window_gev"]))
        sigma_range = eta_ref["sigma_over_mass"]
        if fit.get("status") == "fit_ok":
            ratio = fit["sigma_gev"] / fit["mean_gev"]
            passed = sigma_range[0] <= ratio <= sigma_range[1]
        else:
            ratio = None
            passed = False
        eta_results.append(
            {
                "abs_eta": [low, high],
                "fit": fit,
                "sigma_over_mass": ratio,
                "published_plot_envelope": sigma_range,
                "passed": passed,
            }
        )
    result["jpsi_resolution_by_abs_eta"] = eta_results
    result["passed"] = (
        result["z_dimuon"]["passed"]
        and all(
            item["heldout_reference_gate"].get("passed", False) for item in result["fits"].values()
        )
        and all(row["passed"] for row in eta_results)
    )
    result["status"] = (
        "passed_reference_regression" if result["passed"] else "failed_reference_regression"
    )
    result["interpretation"] = (
        "A passing status means only that this frozen held-out event sample meets the "
        "predeclared reference regression gates. It does not establish detector calibration "
        "or validate the HEPLab simulator."
    )
    result["deterministic_result_sha256"] = hashlib.sha256(
        json.dumps(
            _stable_result_value(
                {
                    "z_dimuon": {
                        "template_fit": result["z_dimuon"]["template_fit"],
                        "heldout_template_closure": result["z_dimuon"]["heldout_template_closure"],
                    },
                    "fits": result["fits"],
                    "jpsi_resolution_by_abs_eta": result["jpsi_resolution_by_abs_eta"],
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf8")
    ).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="local NanoAOD ROOT path (defaults to CMS Open Data URL)")
    parser.add_argument(
        "--from-pairs",
        type=Path,
        help="re-fit a frozen selected-pairs.json offline (provenance is read beside it)",
    )
    parser.add_argument(
        "--provenance",
        type=Path,
        help="v2 source report paired with --from-pairs (defaults to sibling validation.json)",
    )
    parser.add_argument("--entry-start", type=int, default=DEFAULT_ENTRY_START)
    parser.add_argument("--entries", type=int, default=DEFAULT_ENTRY_COUNT)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "artifacts/cms/resonance-validation-v2"
    )
    args = parser.parse_args()
    if args.from_pairs:
        rows = json.loads(args.from_pairs.read_text(encoding="utf8"))
        prior_report = json.loads(
            (args.provenance or args.from_pairs.with_name("validation.json")).read_text(
                encoding="utf8"
            )
        )
        if prior_report.get("schema") != "heplab-cms-data-resonance-validation-v2":
            raise ValueError("--from-pairs requires a target-independent v2 selected-pairs fixture")
        prior_source = prior_report["source"]
        if digest_file(args.from_pairs) != prior_source["selected_pairs_sha256"]:
            raise ValueError("frozen resonance candidate sample does not match its provenance")
        counts = prior_source["trigger_counts_and_candidates"]
        source_provenance = prior_source
    else:
        source = args.input or SOURCE
        dataset_manifest = yaml.safe_load(DATASET_MANIFEST.read_text(encoding="utf8"))
        source_record = next(
            item
            for item in dataset_manifest["files"]
            if item["filename"] == "05DD095C-F6C3-9A4F-9FB3-348A5A6403D5.root"
        )
        prior_source = {
            "declared_adler32": source_record["adler32"],
            "source_size_bytes": source_record["size_bytes"],
        }
        if source == SOURCE and source_record["url"] != SOURCE:
            raise ValueError("dataset manifest URL differs from the frozen CMS source URL")
        integrity = verify_source(source, prior_source)
        if args.entry_start < 0 or args.entries <= 0:
            raise ValueError("--entry-start must be nonnegative and --entries must be positive")
        entry_stop = args.entry_start + args.entries
        rows, counts = extract_pairs(source, args.entry_start, entry_stop)
        source_provenance = {
            "url": str(source),
            "record": 30522,
            "entry_start": counts["entry_start"],
            "entry_stop": counts["entry_stop"],
            "input_entries_available": counts["entries_read"],
            "trigger_counts_and_candidates": counts,
            "candidate_selection_algorithm": "maximum-scalar-pT-sum-v1",
            "event_split_algorithm": EVENT_SPLIT_ALGORITHM,
            "split_fraction_heldout": 0.2,
            "trigger_paths": TRIGGERS,
            "source_adler32": prior_source["declared_adler32"],
            "source_size_bytes": prior_source["source_size_bytes"],
            "source_integrity": integrity,
            "dataset_manifest_sha256": digest_file(DATASET_MANIFEST),
            "certification_sha256": digest_file(CERTIFICATION),
            "extractor_git_revision": git_revision(),
            "python": platform.python_version(),
            "uproot": uproot.__version__,
            "awkward": ak.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "environment_lock_sha256": digest_file(ROOT / "uv.lock"),
            "git_dirty": git_dirty(),
            "container_digest": None,
            "execution_environment": platform.platform(),
        }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs_path = args.output_dir / "selected-pairs.json"
    if not args.from_pairs or pairs_path.resolve() != args.from_pairs.resolve():
        pairs_path.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf8")
    source_provenance["selected_pairs_sha256"] = digest_file(pairs_path)
    report = report_from_rows(rows, source_provenance)
    report["validation_environment"] = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "environment_lock_sha256": digest_file(ROOT / "uv.lock"),
        "git_revision": git_revision(),
        "git_dirty": git_dirty(),
        "container_digest": None,
        "execution_environment": platform.platform(),
    }
    report_path = args.output_dir / "validation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(
        json.dumps(
            {
                "counts": counts,
                "passed": report["passed"],
                "fits": report["fits"],
                "eta": report["jpsi_resolution_by_abs_eta"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
