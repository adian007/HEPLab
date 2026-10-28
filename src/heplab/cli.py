"""HEPLab command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__, catalog

ROADMAP = {
    "aod": ("Phase 4–5", "ADR-0003"),
}


def _manifests_dir() -> Path:
    return catalog.manifests_dir()


def _load_manifest(path: Path) -> dict:
    return catalog.read_manifest(path)


def _analysis_dir(name: str) -> Path:
    path = Path(__file__).resolve().parent / "analyses" / name
    if not path.is_dir():
        raise ValueError(f"unknown analysis {name!r}; available: dimuon")
    return path


def _read_events(args, lumi_mask=None):
    from itertools import islice

    from .io.provenance import file_hash
    from .io.xrootd import iter_chunks, load_manifest

    ranges = []
    if args.max_events is not None and args.max_events <= 0:
        raise ValueError("event limit must be positive")
    if args.input:
        path = Path(args.input).expanduser()
        identity = file_hash(path)
        if path.suffix.lower() == ".json":
            if path.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("JSON fixture exceeds 64 MiB; use a chunked ROOT source")

            def reject(value):
                raise ValueError(f"nonfinite JSON input: {value}")

            data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)
            events = data.get("events", data) if isinstance(data, dict) else data
            if not isinstance(events, list):
                raise ValueError("JSON input must contain schema event records")
            rows = islice(events, args.max_events)
        elif path.suffix.lower() == ".root":
            from .readers import get_reader

            rows = get_reader(args.format)(
                str(path),
                entry_stop=args.max_events,
                is_data=not args.simulation,
                source_id=identity,
            )
        else:
            raise ValueError("input must be local JSON or ROOT")

        def local_events():
            count = 0
            for index, event in enumerate(rows):
                info = event["EventInfo"]
                info.update(source_id=identity, source_entry=index)
                if lumi_mask and info.get("is_data"):
                    info["certified"] = lumi_mask.accepts(info["run"], info["luminosity_block"])
                    info["certification_sha256"] = lumi_mask.sha256
                count += 1
                yield event
            ranges.append(
                {
                    "source_id": identity,
                    "entry_start": 0,
                    "entry_stop": count,
                    "integrity": "full_file_verified",
                    "sha256": identity,
                }
            )

        return local_events(), path.stem, identity, ranges
    manifest, path = load_manifest(args.dataset)

    def remote_events():
        for descriptor, chunk in iter_chunks(
            args.dataset,
            sample=args.max_events,
            cache=not args.no_cache,
            is_data=False if args.simulation else None,
            lumi_mask=lumi_mask,
        ):
            ranges.append(descriptor)
            yield from chunk

    return remote_events(), manifest.get("name", args.dataset), file_hash(path), ranges


def cmd_version(_args: argparse.Namespace) -> int:
    print(f"heplab {__version__}")
    return 0


def cmd_catalog_list(_args: argparse.Namespace) -> int:
    mdir = _manifests_dir()
    if not mdir.is_dir():
        print(f"no manifests directory at {mdir}", file=sys.stderr)
        return 1
    files = sorted(mdir.glob("*.yaml"))
    if not files:
        print("catalog is empty")
        return 0
    print(f"{'name':<26} {'record':<12} note")
    for path in files:
        manifest = _load_manifest(path)
        note = manifest.get("note", "")
        print(
            f"{manifest.get('name', path.stem):<26} {str(manifest.get('record', '?')):<12} {note}"
        )
    return 0


def cmd_catalog_info(args: argparse.Namespace) -> int:
    try:
        manifest, _ = catalog.get(args.dataset)
    except KeyError:
        print(f"dataset {args.dataset!r} not found", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .io.xrootd import iter_chunks

    chunks = iter_chunks(
        args.dataset,
        sample=args.sample,
        cache=not args.no_cache,
        chunk_size=args.chunk_size,
        is_data=False if args.simulation else None,
    )
    count = sum(len(events) for _, events in chunks)
    print(f"Fetched {count} events for {args.dataset}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    import yaml

    from .analyses.dimuon.run import process
    from .io.artifacts import publish
    from .io.certification import LumiMask
    from .io.provenance import ProvenanceStamp, config_hash, source_snapshot

    analysis_dir = _analysis_dir(args.analysis)
    config_path = Path(args.config) if args.config else analysis_dir / "config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if args.trigger:
        config["trigger"] = {"paths": args.trigger}
    if args.measurement:
        config["validation"] = {"mode": "measurement"}
    certification = args.certification
    if certification is None and not args.input:
        manifest, manifest_path = catalog.get(args.dataset)
        cert = manifest.get("certification")
        if cert:
            from .io.provenance import file_hash

            candidate = (manifest_path.parent.parent / cert["path"]).resolve()
            if candidate.parent != (manifest_path.parent.parent / "certification").resolve():
                raise ValueError("certification path escapes catalog root")
            if file_hash(candidate) != cert["sha256"]:
                raise ValueError("certification payload checksum mismatch")
            certification = str(candidate)
    mask = LumiMask(certification) if certification else None
    events, dataset_name, manifest_hash, ranges = _read_events(args, mask)
    result = process(events, config)
    stamp = ProvenanceStamp(
        schema_version=1,
        git_sha=ProvenanceStamp.current_git_sha(),
        config_sha256=config_hash(config),
        dataset_manifest_hash=manifest_hash,
        source_tree_sha256=source_snapshot(),
        source_ranges=tuple(ranges),
        certification_sha256=mask.sha256 if mask else "",
        validation=result["validation"]["mode"],
        file_checksums=tuple(
            r.get("declared_checksum", {}).get("value", r.get("sha256", "")) for r in ranges
        ),
    )
    result["dataset"] = dataset_name
    result["provenance"] = stamp.to_dict()
    result["provenance_digest"] = stamp.digest()
    result["created_at"] = datetime.now(UTC).isoformat()
    result["payload_content_sha256"] = config_hash(result)
    output = Path(
        args.output or f"artifacts/{args.analysis}-{result['payload_content_sha256'][:16]}.json"
    )
    publish(output, result)
    print(
        f"Processed {result['events_processed']} events; "
        f"selected {result['histogram']['entries']} dimuon pairs"
    )
    print(f"Artifact: {output.resolve()}")
    return 0


def cmd_plot(args: argparse.Namespace) -> int:
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("plotting requires matplotlib; install `heplab[analysis]`") from exc
    hist = artifact["histogram"]
    low, high = hist["range"]
    bins = hist["bins"]
    edges = hist.get("edges", [low + (high - low) * i / bins for i in range(bins + 1)])
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.stairs(hist["counts"], edges, fill=True, alpha=0.45)
    ax.set(
        xlabel="m(μμ) [GeV]",
        ylabel="Events",
        title=f"Dimuon spectrum — {artifact.get('dataset', 'input')}",
    )
    target = Path(args.output or str(Path(args.artifact).with_suffix(".png")))
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=160, bbox_inches="tight")
    print(f"Plot: {target.resolve()}")
    return 0


def cmd_fit(args: argparse.Namespace) -> int:
    from .stats.fits import FitBackend, unbinned_fit

    artifact_path = Path(args.artifact)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if artifact.get("multi_candidate_events", 0):
        raise ValueError("unbinned independent-observation fit rejects clustered multi-pair events")
    result = unbinned_fit(
        {
            "values": artifact.get("masses", []),
            "weights": artifact.get("candidate_weights", []),
            "range": args.range,
        },
        FitBackend.GPU if args.backend == "gpu" else FitBackend.CPU,
    )
    from .io.artifacts import publish
    from .io.provenance import file_hash

    child = {"fit": result, "parent_sha256": file_hash(artifact_path)}
    output = (
        Path(args.output)
        if args.output
        else artifact_path.with_name(artifact_path.stem + "-fit.json")
    )
    if output.resolve() == artifact_path.resolve():
        raise ValueError("fit output cannot replace its parent")
    publish(output, child)
    print(json.dumps(result, indent=2))
    return 0


def cmd_closure(args: argparse.Namespace) -> int:
    from .analyses.closure import compare

    report = compare(args.data, args.sim)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Closure report: {output.resolve()}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("serving needs uvicorn; install `heplab[serve]`") from exc
    from .server.app import create_app

    if getattr(args, "open_browser", False):
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=(f"http://127.0.0.1:{args.port}/workbench",)).start()
    uvicorn.run(create_app(args.artifacts), host="127.0.0.1", port=args.port)
    return 0


def cmd_sim(args: argparse.Namespace) -> int:
    from .sim import generate, simulate

    if args.sim_action == "chain":
        from .sim.pipeline import run_chain

        print(run_chain(output=args.output, events=args.events, seed=args.seed))
    elif args.sim_action == "doctor":
        from .sim.pipeline import runtime

        print(json.dumps(runtime(), indent=2))
    elif args.sim_action == "generate":
        print(generate(output=args.output, events=args.events, seed=args.seed))
    elif args.sim_action == "simulate":
        print(simulate(input=args.input, output=args.output))
    else:
        raise ValueError("sim action must be generate or simulate")
    return 0


def cmd_engine(args):
    from .physics.engine import capabilities, execute

    if args.engine_action == "capabilities":
        print(json.dumps(capabilities(), indent=2))
    else:
        request = json.loads(Path(args.request).read_text(encoding="utf8"))
        print(json.dumps(execute(request, backend=args.backend), indent=2, allow_nan=False))
    return 0


def cmd_lab(args):
    from .lab.profile import load_profile, profile_summary

    if args.lab_action == "profile":
        print(json.dumps(profile_summary(load_profile(args.profile)), indent=2))
    else:
        from .lab.replay import replay

        record = replay(
            args.profile,
            args.raw,
            args.output,
            offsets_path=args.offsets,
            window_ns=args.window_ns,
            trigger_source=args.trigger_source,
        )
        print(json.dumps({"output": args.output, "blocked": record["blocked_stages"]}))
    return 0


def cmd_stub(verb: str):
    def handler(_args: argparse.Namespace) -> int:
        phase, adr = ROADMAP[verb]
        print(f"heplab {verb}: not implemented yet — planned for {phase} ({adr}).")
        print("Roadmap: docs/PROJECT.md §7 · Decisions: docs/adr/README.md")
        return 2

    return handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="heplab", description="Reproducible LHC analysis and simulation on CERN Open Data."
    )
    parser.add_argument("--version", action="version", version=f"heplab {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="print the heplab version").set_defaults(func=cmd_version)
    engine = sub.add_parser("engine", help="checked analytic and educational physics core")
    engine_sub = engine.add_subparsers(dest="engine_action", required=True)
    engine_sub.add_parser("capabilities").set_defaults(func=cmd_engine)
    engine_run = engine_sub.add_parser("run")
    engine_run.add_argument("request")
    engine_run.add_argument("--backend", choices=["reference", "rust"], default="reference")
    engine_run.set_defaults(func=cmd_engine)
    catalog = sub.add_parser("catalog", help="browse dataset manifests")
    catalog_sub = catalog.add_subparsers(dest="subcommand", required=True)
    catalog_sub.add_parser("list").set_defaults(func=cmd_catalog_list)
    info = catalog_sub.add_parser("info")
    info.add_argument("dataset")
    info.set_defaults(func=cmd_catalog_info)
    fetch = sub.add_parser("fetch", help="read a verified dataset manifest into the local cache")
    fetch.add_argument("dataset")
    fetch.add_argument("--sample", help="exact positive source event count")
    fetch.add_argument("--chunk-size", type=int, default=100_000)
    fetch.add_argument("--simulation", action="store_true")
    fetch.add_argument("--no-cache", action="store_true")
    fetch.set_defaults(func=cmd_fetch)
    run = sub.add_parser("run", help="run a supported analysis")
    run.add_argument("analysis", choices=["dimuon"])
    run.add_argument("--dataset", default="Run2016G_DoubleMuon")
    run.add_argument("--certification", help="frozen CMS good-lumi JSON")
    run.add_argument(
        "--trigger", action="append", help="required recorded trigger path; repeat for OR"
    )
    run.add_argument(
        "--measurement", action="store_true", help="require certification and trigger provenance"
    )
    run.add_argument("--input", help="local schema JSON or NanoAOD ROOT file")
    run.add_argument("--config")
    run.add_argument("--output")
    run.add_argument("--max-events", type=int)
    run.add_argument("--simulation", action="store_true")
    run.add_argument("--format", choices=["nanoaod", "delphes"], default="nanoaod")
    run.add_argument("--no-cache", action="store_true")
    run.set_defaults(func=cmd_run)
    plot = sub.add_parser("plot", help="render a result artifact")
    plot.add_argument("artifact")
    plot.add_argument("--output")
    plot.set_defaults(func=cmd_plot)
    fit = sub.add_parser("fit", help="fit the dimuon mass spectrum in an artifact")
    fit.add_argument("artifact")
    fit.add_argument("--output", help="new child artifact path")
    fit.add_argument("--range", nargs=2, type=float, default=[70, 110])
    fit.add_argument("--backend", choices=["cpu", "gpu"], default="cpu")
    fit.set_defaults(func=cmd_fit)
    sim = sub.add_parser("sim", help="run the external PYTHIA8/DELPHES container")
    sim_sub = sim.add_subparsers(dest="sim_action", required=True)
    chain = sim_sub.add_parser("chain", help="registered pp DY -> PYTHIA8 -> CMS DELPHES")
    chain.add_argument("--output", required=True, help="new immutable run directory")
    chain.add_argument("--events", type=int, default=100)
    chain.add_argument("--seed", type=int, default=42)
    chain.set_defaults(func=cmd_sim)
    doctor = sim_sub.add_parser("doctor", help="inspect pinned local simulation runtime")
    doctor.set_defaults(func=cmd_sim)
    generate = sim_sub.add_parser("generate")
    generate.add_argument("--output", default="data/generated.hepmc")
    generate.add_argument("--events", type=int, default=10_000)
    generate.add_argument("--seed", type=int, default=42)
    generate.set_defaults(func=cmd_sim)
    simulate = sim_sub.add_parser("simulate")
    simulate.add_argument("--input", required=True)
    simulate.add_argument("--output", default="data/delphes.root")
    simulate.set_defaults(func=cmd_sim)
    lab = sub.add_parser("lab", help="laboratory detector profiles and offline replay")
    lab_sub = lab.add_subparsers(dest="lab_action", required=True)
    lab_profile = lab_sub.add_parser("profile", help="check a device profile and list unknowns")
    lab_profile.add_argument("profile")
    lab_profile.set_defaults(func=cmd_lab)
    lab_replay = lab_sub.add_parser("replay", help="replay a recorded raw file; no hardware access")
    lab_replay.add_argument("--profile", required=True)
    lab_replay.add_argument("--raw", required=True)
    lab_replay.add_argument("--output", required=True, help="new immutable run record JSON")
    lab_replay.add_argument("--offsets", help="channel offsets derived for this profile")
    lab_replay.add_argument("--window-ns", type=float, default=25.0)
    lab_replay.add_argument("--trigger-source", help="independent trigger id for efficiency")
    lab_replay.set_defaults(func=cmd_lab)
    closure = sub.add_parser("closure", help="compare data and simulation artifacts")
    closure.add_argument("data")
    closure.add_argument("sim")
    closure.add_argument("--output", default="artifacts/closure.json")
    closure.set_defaults(func=cmd_closure)
    serve = sub.add_parser("serve", help="start the API on localhost")
    serve.add_argument("--artifacts", default="artifacts")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)
    gui = sub.add_parser("gui", help="open the local simulator workbench")
    gui.add_argument("--artifacts", default="artifacts/workbench")
    gui.add_argument("--port", type=int, default=8765)
    gui.add_argument("--open-browser", action="store_true")
    gui.set_defaults(func=cmd_serve)
    for verb in ROADMAP:
        command = sub.add_parser(verb, help=f"planned {ROADMAP[verb][0]} interface")
        command.add_argument("args", nargs="*")
        command.set_defaults(func=cmd_stub(verb))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (
        ValueError,
        TypeError,
        LookupError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"heplab: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
