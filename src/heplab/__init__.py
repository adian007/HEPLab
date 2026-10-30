"""HEPLab — reproducible LHC analysis and simulation on CERN Open Data.

Optional scientific dependencies are loaded only by functions that need them,
so catalog and local JSON workflows remain usable with the small core install.
See docs/PROJECT.md, docs/ARCHITECTURE.md, and docs/adr/README.md.
"""

__version__ = "0.1.0.dev0"
API_VERSION = "1"

__all__ = [
    "__version__",
    "API_VERSION",
    "export_html",
    "fit_peak",
    "labs",
    "load",
    "notebook",
    "read",
    "run",
]


def run(events, *, analysis: str = "dimuon", config: dict | None = None) -> dict:
    """Run a supported analysis over normalized HEPLab event records.

    ``events`` may be any iterable of the versioned schema's event dictionaries.
    The returned mapping is an in-memory result; use :func:`load` for published
    artifacts and the CLI when source acquisition or artifact publication is needed.
    """
    if analysis != "dimuon":
        raise ValueError(f"unsupported analysis {analysis!r}; available: dimuon")
    import hashlib
    import json

    from .analyses.dimuon.run import process
    from .io.provenance import config_hash

    digest = hashlib.sha256()
    count = 0
    sources: set[str] = set()
    certifications: set[str] = set()

    def tracked_events():
        nonlocal count
        for event in events:
            try:
                encoded = json.dumps(
                    event, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"event is not finite JSON data: {exc}") from exc
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
            count += 1
            source = event.get("EventInfo", {}).get("source_id")
            cert = event.get("EventInfo", {}).get("certification_sha256")
            if source:
                sources.add(str(source))
            if cert:
                certifications.add(str(cert))
            yield event

    result = process(tracked_events(), config or {})
    result["provenance"] = {
        "schema": "heplab-python-provenance-v1",
        "kind": "in_memory_events",
        "event_count": count,
        "input_events_sha256": digest.hexdigest(),
        "analysis_config_sha256": config_hash(config or {}),
        "api_version": API_VERSION,
        "heplab_version": __version__,
        "source_ids": sorted(sources),
        "certification_sha256": sorted(certifications),
    }
    hash_excluded = {
        "dataset",
        "provenance",
        "provenance_digest",
        "created_at",
        "reproduction",
        "result_sha256",
        "payload_content_sha256",
    }
    result["result_sha256"] = config_hash(
        {key: value for key, value in result.items() if key not in hash_excluded}
    )
    return result


def load(path):
    """Load a published JSON artifact and verify its canonical content digest."""
    import json
    from pathlib import Path

    from .io.provenance import config_hash

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("HEPLab artifact must contain a JSON object")
    expected = value.get("payload_content_sha256")
    if expected:
        content = dict(value)
        del content["payload_content_sha256"]
        actual = config_hash(content)
        if actual != expected:
            raise ValueError("artifact content digest mismatch")
    result_hash = value.get("result_sha256")
    if result_hash:
        result = dict(value)
        for key in (
            "dataset",
            "provenance",
            "provenance_digest",
            "created_at",
            "reproduction",
            "result_sha256",
            "payload_content_sha256",
        ):
            result.pop(key, None)
        if config_hash(result) != result_hash:
            raise ValueError("deterministic result digest mismatch")
    return value


def read(
    path,
    *,
    simulation: bool = False,
    max_events: int | None = None,
    format: str = "nanoaod",
) -> list[dict]:
    """Read a local JSON event list or ROOT file into schema event dictionaries.

    JSON may be a list of events or ``{"events": [...]}``. ROOT files use the
    named reader (``nanoaod`` or ``delphes``). ``simulation`` declares the
    source kind for events that do not carry their own flag; reading a NanoAOD
    simulation file without it raises, so data and simulation are never mixed up.
    """
    import json
    from itertools import islice
    from pathlib import Path

    source = Path(path).expanduser()
    if max_events is not None and max_events <= 0:
        raise ValueError("max_events must be positive")
    if source.suffix.lower() == ".json":

        def reject(value):
            raise ValueError(f"nonfinite JSON input: {value}")

        data = json.loads(source.read_text(encoding="utf-8"), parse_constant=reject)
        events = data.get("events", data) if isinstance(data, dict) else data
        if not isinstance(events, list):
            raise ValueError("JSON input must contain schema event records")
        rows = list(islice(events, max_events))
        for event in rows:
            info = event.setdefault("EventInfo", {})
            if "is_data" not in info and info.get("kind") not in {"data", "simulation"}:
                info["is_data"] = not simulation
        return rows
    if source.suffix.lower() == ".root":
        from .readers import get_reader

        return list(get_reader(format)(str(source), entry_stop=max_events, is_data=not simulation))
    raise ValueError("input must be a local .json or .root file")


def fit_peak(result: dict, *, window: tuple[float, float] = (70.0, 110.0)) -> dict:
    """Fit the dimuon mass peak of a :func:`run` result (Gaussian on a flat background).

    Requires ``heplab[analysis]`` (iminuit). Returns the fit record: ``values``
    and ``errors`` hold ``mean``, ``sigma`` and ``signal_fraction``; ``success``
    says whether the minimiser converged with an accurate covariance.
    """
    from .stats.fits import unbinned_fit

    masses = result.get("masses")
    if not isinstance(masses, list):
        raise ValueError("result has no per-candidate masses; pass a heplab.run() result")
    weights = result.get("candidate_weights") or [1.0] * len(masses)
    if any(weight != 1 for weight in weights):
        raise ValueError("fit_peak supports unweighted candidates only")
    return unbinned_fit({"values": masses, "range": list(window)})


def export_html(result, output, *, title: str | None = None, include_raw: bool = False):
    """Write a result (or artifact path) as one self-contained, offline HTML page."""
    from .export.web_page import export_html as export

    return export(result, output, title=title, include_raw=include_raw)


def __getattr__(name: str):
    # Submodules with optional dependencies load on first use.
    if name in {"labs", "notebook"}:
        import importlib

        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module 'heplab' has no attribute {name!r}")
