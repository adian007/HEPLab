"""HEPLab command-line interface."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
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
                # Unflagged JSON records take the command's declared kind, so data
                # is never silently relabelled as simulation (and skips certification).
                if "is_data" not in info and info.get("kind") not in {"data", "simulation"}:
                    info["is_data"] = not args.simulation
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
    from .io.provenance import (
        ProvenanceStamp,
        config_hash,
        container_digest,
        environment_lock_hash,
        source_snapshot,
    )

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
    deterministic_hash = config_hash(result)
    stamp = ProvenanceStamp(
        schema_version=1,
        git_sha=ProvenanceStamp.current_git_sha(),
        config_sha256=config_hash(config),
        dataset_manifest_hash=manifest_hash,
        container_digest=container_digest(),
        source_tree_sha256=source_snapshot(),
        source_ranges=tuple(ranges),
        certification_sha256=mask.sha256 if mask else "",
        validation=result["validation"]["mode"],
        file_checksums=tuple(
            r.get("declared_checksum", {}).get("value", r.get("sha256", "")) for r in ranges
        ),
        environment_lock_sha256=environment_lock_hash(),
        git_dirty=ProvenanceStamp.current_git_dirty(),
        result_sha256=deterministic_hash,
    )
    result["dataset"] = dataset_name
    result["provenance"] = stamp.to_dict()
    result["provenance_digest"] = stamp.digest()
    result["result_sha256"] = deterministic_hash
    result["reproduction"] = {
        "schema": "heplab-reproduction-recipe/v1",
        "analysis": args.analysis,
        "config": config,
        "dataset": None if args.input else args.dataset,
        "input_path": str(Path(args.input).expanduser().resolve()) if args.input else None,
        "input_sha256": manifest_hash if args.input else None,
        "certification_path": (
            str(Path(certification).expanduser().resolve()) if certification else None
        ),
        "certification_sha256": mask.sha256 if mask else None,
        "format": args.format,
        "max_events": args.max_events,
        "simulation": args.simulation,
        "no_cache": args.no_cache,
        "trigger": args.trigger or [],
        "measurement": args.measurement,
    }
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


def cmd_reproduce(args: argparse.Namespace) -> int:
    from .io.provenance import environment_lock_hash, file_hash, source_snapshot

    artifact_path = Path(args.artifact).expanduser().resolve()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(artifact, dict):
        raise ValueError("artifact must contain a JSON object")
    recipe = artifact.get("reproduction")
    provenance = artifact.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ValueError("artifact provenance is invalid")
    if not isinstance(recipe, dict) or recipe.get("schema") != "heplab-reproduction-recipe/v1":
        raise ValueError("artifact does not contain a supported reproduction recipe")
    if recipe.get("analysis") != "dimuon" or not isinstance(recipe.get("config"), dict):
        raise ValueError("artifact reproduction recipe has an unsupported analysis or config")
    if provenance.get("environment_lock_sha256") != environment_lock_hash():
        raise ValueError("dependency lock identity differs from the recorded environment")
    if provenance.get("source_tree_sha256") != source_snapshot():
        raise ValueError(
            "source tree differs from the recorded run; check out its recorded revision"
        )
    if recipe.get("input_path"):
        input_path = Path(recipe["input_path"])
        if not input_path.is_file() or file_hash(input_path) != recipe.get("input_sha256"):
            raise ValueError("recorded local input is missing or has changed")
    cert_path = recipe.get("certification_path")
    if cert_path and (
        not Path(cert_path).is_file()
        or file_hash(cert_path) != recipe["certification_sha256"]
    ):
        raise ValueError("recorded certification file is missing or has changed")
    with tempfile.TemporaryDirectory(prefix="heplab-reproduce-") as temporary:
        config_path = Path(temporary) / "analysis.json"
        output_path = Path(temporary) / "result.json"
        config_path.write_text(json.dumps(recipe["config"], sort_keys=True), encoding="utf-8")
        run_args = argparse.Namespace(
            analysis=recipe["analysis"],
            dataset=recipe.get("dataset") or "Run2016G_DoubleMuon",
            certification=cert_path,
            trigger=recipe.get("trigger", []),
            measurement=recipe.get("measurement", False),
            input=recipe.get("input_path"),
            config=str(config_path),
            output=str(output_path),
            max_events=recipe.get("max_events"),
            simulation=recipe.get("simulation", False),
            format=recipe.get("format", "nanoaod"),
            no_cache=recipe.get("no_cache", False),
        )
        cmd_run(run_args)
        reproduced = json.loads(output_path.read_text(encoding="utf-8"))
    expected = provenance.get("result_sha256") or artifact.get("result_sha256")
    actual = reproduced.get("result_sha256")
    if actual != expected:
        raise ValueError(f"reproduction mismatch: expected {expected}, got {actual}")
    print(f"Reproduced {artifact_path.name}: {actual}")
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


def cmd_export_usd(args) -> int:
    from .export.usd import export_event

    payload = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    output = args.output or Path(args.artifact).with_suffix(".usd")
    print(json.dumps(export_event(payload, output), indent=2))
    return 0


def cmd_export_html(args) -> int:
    from .export.web_page import export_html

    output = args.output or Path(args.artifact).with_suffix(".html")
    page = export_html(args.artifact, output, title=args.title, include_raw=args.include_raw)
    print(f"Page: {page.resolve()}")
    return 0


def cmd_gallery(args) -> int:
    from .export.web_page import build_gallery

    print(f"Gallery: {build_gallery(args.directory, title=args.title).resolve()}")
    return 0


def cmd_learn(args) -> int:
    from . import fit_peak, labs, load

    if args.learn_command == "list":
        for entry in labs.available():
            print(
                f"{entry['id']:12} {entry['title']} ({entry['duration_minutes']} min)"
                f" - {entry['audience']}"
            )
        return 0
    lab = labs.start(args.lab)
    if args.learn_command == "show":
        print(lab.title, lab.spec["summary"], "", sep="\n")
        for index, step in enumerate(lab.steps, 1):
            print(f"{index}. [{step['id']}] {step['title']}", f"   {step['task']}", sep="\n")
            for key, text in step.get("choices", {}).items():
                print(f"     {key}) {text}")
        return 0
    if args.learn_command == "practice-data":
        events = labs.practice_events(args.events, seed=args.seed)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"events": events}), encoding="utf-8")
        print(f"Wrote {len(events)} synthetic practice events (not CMS data) to {output.resolve()}")
        print(f"Next: heplab run dimuon --simulation --input {output} --output artifacts/z.json")
        return 0
    # check: grade the histogram and fit steps from a published dimuon artifact.
    result = load(args.artifact)
    feedback = [lab.check("histogram", result)]
    try:
        feedback.append(lab.check("fit", fit_peak(result)))
    except (ValueError, RuntimeError) as exc:
        print(f"fit step skipped: {exc}")
    for item in feedback:
        print(item)
    return 0 if all(item.passed for item in feedback) else 1


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

        threading.Timer(
            1.0, webbrowser.open, args=(f"http://127.0.0.1:{args.port}/workbench",)
        ).start()
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
    reproduce = sub.add_parser("reproduce", help="rerun an artifact and verify its result hash")
    reproduce.add_argument("artifact", help="HEPLab artifact with a reproduction recipe")
    reproduce.set_defaults(func=cmd_reproduce)
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
    usd = sub.add_parser("export-usd", help="write a workbench event display as an OpenUSD stage")
    usd.add_argument("artifact", help="workbench run/event JSON with 'tracks' and 'geometry'")
    usd.add_argument("--output", help="target .usd path (default: artifact with .usd suffix)")
    usd.set_defaults(func=cmd_export_usd)
    page = sub.add_parser("export-html", help="write a result as a self-contained offline web page")
    page.add_argument("artifact", help="published result artifact or workbench run JSON")
    page.add_argument("--output", help="target .html path (default: artifact with .html suffix)")
    page.add_argument("--title")
    page.add_argument("--include-raw", action="store_true", help="embed per-candidate arrays")
    page.set_defaults(func=cmd_export_html)
    gallery = sub.add_parser("gallery", help="index exported pages in a directory")
    gallery.add_argument("directory")
    gallery.add_argument("--title", default="HEPLab gallery")
    gallery.set_defaults(func=cmd_gallery)
    learn = sub.add_parser("learn", help="guided physics labs with step checks")
    learn_sub = learn.add_subparsers(dest="learn_command", required=True)
    learn_sub.add_parser("list", help="installed labs")
    for name, text in (
        ("show", "print a lab's steps"),
        ("practice-data", "write the offline practice sample"),
        ("check", "grade the histogram and fit steps from an artifact"),
    ):
        command = learn_sub.add_parser(name, help=text)
        command.add_argument("lab", nargs="?", default="z-boson")
        if name == "practice-data":
            command.add_argument("--output", default="artifacts/z-practice-events.json")
            command.add_argument("--events", type=int, default=4000)
            command.add_argument("--seed", type=int, default=2026)
        if name == "check":
            command.add_argument("--artifact", required=True)
    learn.set_defaults(func=cmd_learn)
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
    # Physics text (μ, σ, ≥) must not crash legacy Windows consoles.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
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
