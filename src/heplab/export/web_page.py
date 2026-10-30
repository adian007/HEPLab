# ruff: noqa: E501 -- the page template, stylesheet and script are embedded assets.
"""Export a HEPLab result as one self-contained, offline HTML page.

The page embeds the result as JSON and renders it with a small inline script:
an interactive histogram and cutflow for analysis results, a two-view event
display for workbench runs, and the full provenance record. It loads nothing
from the network, so it can be emailed, archived or attached to a course.

A gallery is a directory of exported pages plus an ``index.html`` built from
the metadata each page carries.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import __version__
from ..io.provenance import config_hash

FORMAT = "heplab-html-export-v2"
LEGACY_FORMAT = "heplab-html-export-v1"
META_ID = "heplab-meta"
# Raw per-candidate arrays can be very large; the histogram already carries them.
DROPPED = ("masses", "candidate_weights")
PRIVATE_KEYS = frozenset(
    {
        "event_rows",
        "raw_events",
        "raw_event_rows",
        "output_directory",
        "source_path",
        "input_path",
        "local_path",
        "artifact_path",
    }
)


def kind(result: dict) -> str:
    if result.get("experiment") == "muon-survival":
        return "lifetime"
    if isinstance(result.get("histogram"), dict) and "edges" in result["histogram"]:
        return "analysis"
    if isinstance(result.get("tracks"), list):
        return "event"
    raise ValueError("result is neither an analysis histogram nor a workbench event")


def _embed(value: Any) -> str:
    from ..desktop.worker import finite

    # NaN/inf become null (JSON has no spelling for them), and JSON inside
    # <script> must not be able to close the element.
    text = json.dumps(finite(value), allow_nan=False, separators=(",", ":"), sort_keys=True)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _title(result: dict, kind_: str) -> str:
    if kind_ == "lifetime":
        config = result.get("config", {})
        return f"Muon survival · {config.get('momentum_gev_c', '?')} GeV/c"
    if kind_ == "analysis":
        name = result.get("analysis", "analysis")
        entries = result.get("histogram", {}).get("entries", 0)
        return f"{name} · {entries} candidates · {result.get('data_kind', 'unknown')}"
    config = result.get("config", {})
    return (
        f"Workbench event · {config.get('momentum_gev', '?')} GeV · seed {config.get('seed', '?')}"
    )


def metadata(result: dict, *, title: str | None = None, include_raw: bool = False) -> dict:
    from ..desktop.worker import finite

    kind_ = kind(result)
    content = _public_result(result, include_raw=include_raw)
    digest = result.get("result_sha256") or config_hash(finite(content))
    artifact = result.get("artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    model_spec = result.get("model_spec")
    model_spec = model_spec if isinstance(model_spec, dict) else {}
    if not model_spec and isinstance(result.get("display_model_spec"), dict):
        model_spec = result["display_model_spec"]
    source = result.get("source")
    source = source if isinstance(source, dict) else artifact.get("source", {})
    source = source if isinstance(source, dict) else {}
    components = model_spec.get("components", [])
    manifest = {
        "schema": "heplab-share-v2",
        "scope": artifact.get("scope", "unscoped_result"),
        "run_id": artifact.get("run_id"),
        "result_sha256": digest,
        "event_index": artifact.get("event_index"),
        "parent_run_sha256": artifact.get("parent_run_sha256"),
        "source": {
            "kind": result.get("data_kind") or source.get("kind") or "declared_or_recorded_sample",
            "record": source.get("record"),
            "file_hashes": source.get("file_hashes", []),
        },
        "configuration": {
            "model_id": [item.get("id") for item in components if isinstance(item, dict)]
            or model_spec.get("id")
            or result.get("model"),
            "seed": (result.get("config") or {}).get("seed"),
            "units": model_spec.get("units", {}),
            "settings": (result.get("config") or {}),
        },
        "software": {
            "heplab": __version__,
            "python": artifact.get("python"),
            "backend": result.get("backend"),
            "generator": artifact.get("generator"),
            "delphes_card_sha256": artifact.get("delphes_card_sha256"),
        },
        "evidence": {
            "status": result.get("validation"),
            "scope": model_spec.get("limitations") or model_spec.get("validation"),
            "references": sorted(
                {
                    reference
                    for item in components
                    if isinstance(item, dict)
                    for reference in item.get("references", [])
                }
            ),
        },
        "privacy": {
            "contains_local_paths": bool(
                include_raw
                and any(
                    isinstance(value, str) and re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?!/))", value)
                    for value in _walk_strings(result)
                )
            ),
            "raw_events_included": bool(
                include_raw
                and any(key in result for key in PRIVATE_KEYS | {"masses", "candidate_weights"})
            ),
        },
    }
    return {
        "format": FORMAT,
        "schema": "heplab-share-v2",
        "kind": kind_,
        "title": title or _title(result, kind_),
        "result_sha256": digest,
        "data_kind": result.get("data_kind")
        or (result["source"].get("kind") if isinstance(result.get("source"), dict) else None),
        "heplab_version": __version__,
        "exported_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest": manifest,
    }


def _public_result(value: Any, *, include_raw: bool = False) -> Any:
    """Remove common raw-event and host-path fields from shareable exports."""
    if include_raw:
        return value
    if isinstance(value, dict):
        return {
            key: _public_result(item)
            for key, item in value.items()
            if key not in DROPPED and key not in PRIVATE_KEYS
        }
    if isinstance(value, list | tuple):
        return [_public_result(item) for item in value]
    if isinstance(value, str) and re.match(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?!/))", value):
        return "[local path omitted from shareable export]"
    return value


def _walk_strings(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list | tuple):
        for child in value:
            yield from _walk_strings(child)
    elif isinstance(value, str):
        yield value


def render(result: dict, *, title: str | None = None, include_raw: bool = False) -> str:
    """Return the page as a string (used by the notebook display too)."""
    if not isinstance(result, dict):
        raise ValueError("result must be a JSON object")
    body = _public_result(result, include_raw=include_raw)
    meta = metadata(result, title=title, include_raw=include_raw)
    return (
        TEMPLATE.replace("__TITLE__", html.escape(meta["title"]))
        .replace("__META__", _embed(meta))
        .replace("__DATA__", _embed(body))
        .replace("__SCRIPT__", SCRIPT)
        .replace("__STYLE__", STYLE)
    )


def export_html(
    result: dict | str | Path,
    output: str | Path,
    *,
    title: str | None = None,
    include_raw: bool = False,
) -> Path:
    """Write ``result`` (a result mapping or an artifact path) to ``output``."""
    from .. import load

    record = result if isinstance(result, dict) else load(result)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(record, title=title, include_raw=include_raw), encoding="utf-8")
    return target


def read_metadata(page: Path) -> dict | None:
    text = page.read_text(encoding="utf-8", errors="replace")
    marker = f'<script type="application/json" id="{META_ID}">'
    start = text.find(marker)
    if start < 0:
        return None
    end = text.find("</script>", start)
    try:
        value = json.loads(text[start + len(marker) : end])
    except ValueError:
        return None
    return (
        value
        if isinstance(value, dict) and value.get("format") in {FORMAT, LEGACY_FORMAT}
        else None
    )


def _read_data(page: Path) -> dict:
    text = page.read_text(encoding="utf-8", errors="replace")
    marker = '<script type="application/json" id="heplab-data">'
    start = text.find(marker)
    if start < 0:
        return {}
    end = text.find("</script>", start)
    try:
        value = json.loads(text[start + len(marker) : end])
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _gallery_preview(value: dict, kind_: str) -> str:
    histogram = value.get("histogram")
    if isinstance(histogram, dict) and isinstance(histogram.get("counts"), list):
        counts = histogram["counts"]
        if not counts:
            return '<div class="preview-empty">No histogram bins</div>'
        width, height, pad = 640, 168, 8
        top = max(max(counts), 1)
        points = [
            f"{pad + (width - pad * 2) * i / max(1, len(counts) - 1):.1f},"
            f"{height - pad - (height - pad * 2) * max(0, float(count)) / top:.1f}"
            for i, count in enumerate(counts)
        ]
        path = "M " + " L ".join(points)
        return (
            '<svg viewBox="0 0 640 168" role="img" aria-label="Mass histogram preview">'
            '<path class="preview-grid" d="M0 42H640 M0 84H640 M0 126H640"/>'
            f'<path class="preview-area" d="{path} L 632 160 L 8 160 Z"/>'
            f'<path class="preview-line" d="{path}"/></svg>'
        )
    tracks = value.get("tracks")
    if isinstance(tracks, list):
        paths = []
        points = [
            point
            for track in tracks
            for point in (track.get("trajectory", {}).get("points") or track.get("points") or [])
        ]
        extent = (
            max((max(abs(float(p[0])), abs(float(p[1]))) for p in points if len(p) >= 2), default=1)
            or 1
        )
        for index, track in enumerate(tracks):
            samples = track.get("trajectory", {}).get("points") or track.get("points") or []
            coords = [
                f"{320 + 270 * float(p[0]) / extent:.1f},{84 - 72 * float(p[1]) / extent:.1f}"
                for p in samples[:: max(1, len(samples) // 90)]
                if len(p) >= 2
            ]
            if coords:
                paths.append(
                    f'<polyline class="event-line line-{index % 2}" points="{" ".join(coords)}"/>'
                )
        return (
            '<svg viewBox="0 0 640 168" role="img" aria-label="Track display preview">'
            '<circle class="event-ring" cx="320" cy="84" r="48"/>'
            '<circle class="event-ring" cx="320" cy="84" r="76"/>' + "".join(paths) + "</svg>"
        )
    return '<div class="preview-empty">HEPLab result</div>'


def build_gallery(directory: str | Path, *, title: str = "HEPLab gallery") -> Path:
    """Index every exported page in ``directory`` into ``index.html``."""
    root = Path(directory)
    entries = []
    for page in sorted(root.glob("*.html")):
        if page.name == "index.html":
            continue
        meta = read_metadata(page)
        if meta is not None:
            entries.append(
                {
                    **meta,
                    "href": page.name,
                    "preview": _gallery_preview(_read_data(page), meta["kind"]),
                }
            )
    entries.sort(key=lambda entry: entry.get("exported_utc", ""), reverse=True)
    cards = "\n".join(
        '<a class="gallery-card" data-kind="{kind}" href="{href}">'
        '<div class="card-top"><span class="kind">{kind_label}</span><span class="digest">{digest}</span></div>'
        '<div class="preview">{preview}</div><div class="card-copy"><h2>{title}</h2>'
        '<p>{description}</p></div><div class="card-foot"><span>Open result <b aria-hidden="true">↗</b></span>'
        "<time>{when}</time></div></a>".format(
            href=html.escape(entry["href"], quote=True),
            kind=html.escape(str(entry.get("kind", "")), quote=True),
            kind_label="MASS ANALYSIS" if entry.get("kind") == "analysis" else "EVENT DISPLAY",
            title=html.escape(str(entry.get("title", entry["href"]))),
            description=(
                "Synthetic teaching sample · dimuon mass spectrum · provenance included"
                if entry.get("kind") == "analysis"
                else "Declared muon fixture · detector response view · provenance included"
            ),
            when=html.escape(str(entry.get("exported_utc", ""))[:10]),
            digest=html.escape(str(entry.get("result_sha256", ""))[:12]),
            preview=entry["preview"],
        )
        for entry in entries
    )
    markup = (
        GALLERY.replace("__TITLE__", html.escape(title))
        .replace("__COUNT__", str(len(entries)))
        .replace("__CARDS__", cards or '<p class="muted">No exported runs yet.</p>')
        .replace("__STYLE__", STYLE)
    )
    index = root / "index.html"
    index.write_text(markup, encoding="utf-8")
    return index


STYLE = """
:root{color-scheme:light dark;--bg:#fff;--surface:#f6f7f7;--surface-raised:#fff;--ink:#1c1b1d;--muted:#505257;--line:#d8dadd;--accent:#087f6c;--accent-soft:#e7f5f1;--accent-2:#8b4f00;--detector-pixel:#2878b8;--detector-tracker:#66869a;--detector-ecal:#b98b18;--detector-hcal:#c56b3e;--detector-muon:#8b6b9f;--detector-solenoid:#b06b24;--grid:#e4e6e8;--shadow:0 1px 3px #1111;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
:root[data-theme=dark]{--bg:#17191e;--surface:#202329;--surface-raised:#252930;--ink:#f2f3f4;--muted:#b4b7bd;--line:#383d46;--accent:#63d6bd;--accent-soft:#193932;--accent-2:#ffc777;--detector-pixel:#82b8ff;--detector-tracker:#72b4c8;--detector-ecal:#f0cc68;--detector-hcal:#ed956c;--detector-muon:#bc9add;--detector-solenoid:#e6a857;--grid:#3d424c;--shadow:0 1px 3px #0004}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#17191e;--surface:#202329;--surface-raised:#252930;--ink:#f2f3f4;--muted:#b4b7bd;--line:#383d46;--accent:#63d6bd;--accent-soft:#193932;--accent-2:#ffc777;--detector-pixel:#82b8ff;--detector-tracker:#72b4c8;--detector-ecal:#f0cc68;--detector-hcal:#ed956c;--detector-muon:#bc9add;--detector-solenoid:#e6a857;--grid:#3d424c;--shadow:0 1px 3px #0004}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:5rem}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.6;font-size:15px}
.site-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:2rem;min-height:4rem;padding:0 max(1.5rem,calc((100vw - 90rem)/2));border-bottom:1px solid var(--line);background:color-mix(in srgb,var(--bg) 94%,transparent);backdrop-filter:blur(12px)}.brand{display:flex;align-items:center;gap:.65rem;min-width:12rem;color:var(--accent);font-weight:700;font-size:1.15rem;text-decoration:none}.brand-mark{width:1.65rem;height:1.65rem}.site-nav{display:flex;align-items:center;gap:1.3rem;flex:1}.site-nav a,.top-link{color:var(--muted);text-decoration:none;font-size:.82rem}.site-nav a:hover,.top-link:hover{color:var(--accent)}.site-actions{display:flex;align-items:center;gap:1rem}.theme-select{padding:.38rem .55rem;border:1px solid var(--line);border-radius:.4rem;background:var(--surface-raised);color:var(--ink);font:inherit;font-size:.75rem}
.doc-layout{display:grid;grid-template-columns:minmax(13rem,18rem) minmax(0,52rem) minmax(12rem,16rem);justify-content:center;min-height:calc(100vh - 4rem)}.sidebar,.toc{position:sticky;top:4rem;align-self:start;height:calc(100vh - 4rem);overflow:auto;padding:1.35rem 1.5rem;border-right:1px solid var(--line)}.toc{border-right:0;border-left:1px solid var(--line)}.nav-heading{margin:0 0 .5rem;color:var(--ink);font-size:.8rem;font-weight:650}.nav-group{margin:0 0 1.35rem}.nav-list{display:grid;gap:.08rem;padding-left:.6rem;border-left:1px solid var(--line)}.nav-list a{display:block;padding:.32rem .45rem;border-radius:.3rem;color:var(--muted);font-size:.78rem;text-decoration:none}.nav-list a:hover{background:var(--accent-soft);color:var(--accent)}.toc a{color:var(--accent);font-size:.76rem;text-decoration:none}.toc p{margin:0 0 .6rem;color:var(--muted);font-size:.76rem}
main.result-content{width:100%;max-width:52rem;margin:0 auto;padding:0 1.5rem 4rem}.page-heading{margin:0 -1.5rem 1.25rem;padding:2.5rem 1.5rem 1.2rem;border-bottom:1px solid var(--line)}h1{margin:.25rem 0 .65rem;font-size:clamp(2rem,4vw,3rem);font-weight:600;line-height:1.12;letter-spacing:-.04em}h2{margin:0 0 .7rem;font-size:1.15rem;font-weight:600;line-height:1.3}.muted{color:var(--muted);font-size:.78rem}.eyebrow{color:var(--accent);font-size:.69rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.page-heading p{margin:0;color:var(--muted);font-size:.78rem;overflow-wrap:anywhere}.result-tag{display:inline-flex;margin-top:.85rem;padding:.2rem .55rem;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:.68rem}
.panel{margin:1rem 0;padding:1rem;border:1px solid var(--line);border-radius:.55rem;background:var(--surface-raised);box-shadow:var(--shadow)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}canvas{display:block;width:100%;height:320px;touch-action:none}
table{width:100%;border-collapse:collapse;font-size:.82rem}td,th{padding:.6rem .65rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}td.num{text-align:right;font-variant-numeric:tabular-nums}code,pre{font-family:ui-monospace,Consolas,monospace;font-size:.8rem}pre{max-height:360px;overflow:auto;margin:0;color:var(--ink);white-space:pre-wrap;word-break:break-all}
.bar{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.65rem}button{padding:.4rem .65rem;border:1px solid var(--line);border-radius:.4rem;background:var(--surface);color:var(--ink);font:inherit;font-size:.75rem;cursor:pointer}button[aria-pressed=true]{border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}button:hover{border-color:var(--accent)}button:focus-visible,a:focus-visible,canvas:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:3px}details summary{color:var(--ink);font-weight:600;cursor:pointer}details[open] summary{margin-bottom:.75rem}
.event-controls{align-items:center;padding:.65rem .75rem;border:1px solid var(--line);border-radius:.45rem;background:var(--surface)}.event-scrub-label{display:flex;align-items:center;gap:.5rem;color:var(--muted);font-size:.74rem}.event-scrubber{width:min(18rem,38vw);accent-color:var(--accent)}
.event-legend{display:flex;flex-wrap:wrap;gap:.45rem 1rem;margin:.75rem 0;color:var(--muted);font-size:.7rem}.event-legend-item{display:inline-flex;align-items:center;gap:.35rem}.event-swatch{display:inline-block;width:.62rem;height:.62rem;border-radius:50%;background:var(--accent)}.event-swatch.pixel{background:var(--detector-pixel)}.event-swatch.tracker{background:var(--detector-tracker)}.event-swatch.ecal{background:var(--detector-ecal)}.event-swatch.hcal{background:var(--detector-hcal)}.event-swatch.muon{background:var(--detector-muon)}.event-swatch.solenoid{background:var(--detector-solenoid)}.event-swatch.charge-positive{background:var(--accent-2)}.event-swatch.charge-negative{background:var(--accent)}
.skip-link{position:absolute;left:-9999px}.skip-link:focus{left:1rem;top:1rem;z-index:20;padding:.6rem;background:var(--surface-raised)}.tip{position:fixed;z-index:15;display:none;pointer-events:none;padding:.35rem .5rem;border:1px solid var(--line);border-radius:.35rem;background:var(--surface-raised);font-size:.8rem;box-shadow:var(--shadow)}
.gallery-hero{display:grid;grid-template-columns:1fr auto;gap:1.5rem;align-items:end;padding:3rem 0 1.5rem}.gallery-hero h1{font-size:clamp(2.5rem,6vw,4rem)}.gallery-hero p{max-width:54ch;color:var(--muted)}.hero-note{max-width:210px;padding:1rem;border-left:2px solid var(--accent);color:var(--muted);font-size:.75rem}.filter-row{display:flex;align-items:center;gap:.5rem;padding:1rem 0;border-top:1px solid var(--line)}.filter-row span{margin-right:.5rem;color:var(--muted);font-size:.7rem}.filter-row button{border-radius:999px}.gallery-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}.gallery-card{display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--line);border-radius:.55rem;background:var(--surface-raised);color:var(--ink);text-decoration:none;transition:border-color .15s,transform .15s}.gallery-card:hover{transform:translateY(-2px);border-color:var(--accent)}.card-top,.card-foot{display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.75rem 1rem}.kind{color:var(--accent);font-size:.65rem;font-weight:700;letter-spacing:.08em}.digest,.card-foot time{color:var(--muted);font:.68rem ui-monospace,monospace}.preview{height:160px;padding:.75rem 1rem;background:var(--surface)}.preview svg{width:100%;height:100%}.preview-grid,.event-ring{fill:none;stroke:var(--line);stroke-width:1}.preview-area{fill:color-mix(in srgb,var(--accent) 20%,transparent)}.preview-line{fill:none;stroke:var(--accent);stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.event-line{fill:none;stroke-width:3;stroke-linecap:round}.line-0{stroke:var(--accent)}.line-1{stroke:var(--accent-2)}.preview-empty{display:grid;height:100%;place-items:center;color:var(--muted)}.card-copy{flex:1;padding:1rem}.card-copy h2{font-size:1.2rem}.card-copy p{margin:0;color:var(--muted);font-size:.8rem}.card-foot{margin-top:.5rem;border-top:1px solid var(--line);color:var(--accent);font-size:.75rem}.gallery-footer{display:flex;justify-content:space-between;gap:1rem;margin-top:2rem;padding-top:1rem;border-top:1px solid var(--line);color:var(--muted);font-size:.72rem}.gallery-card[hidden]{display:none}
@media(max-width:1050px){.doc-layout{grid-template-columns:15rem minmax(0,52rem)}.toc{display:none}}
@media(max-width:700px){.site-header{gap:.75rem;padding:0 1rem}.brand{min-width:0}.site-nav{gap:.7rem}.site-nav a{font-size:.72rem}.site-actions .top-link{display:none}.doc-layout{display:block}.sidebar{display:none}main.result-content{padding:0 1rem 3rem}.page-heading{margin:0 -1rem 1rem;padding:2rem 1rem 1rem}.result-heading{align-items:flex-start;flex-direction:column;padding:1.5rem 0 1rem}.gallery-hero{grid-template-columns:1fr;padding:2rem 0 1rem}.hero-note{max-width:none}.gallery-grid{grid-template-columns:1fr}.gallery-footer{flex-direction:column}canvas{height:260px}}
@media(max-width:420px){.site-header{gap:.55rem}.site-nav{gap:.5rem}.site-nav a:nth-child(2){display:none}.theme-select{max-width:4.8rem}}
"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='27' fill='%23087f6c'/%3E%3Cpath d='M12 32h40M32 12v40' stroke='white' stroke-width='4'/%3E%3C/svg%3E"><style>__STYLE__</style></head>
<body><a class="skip-link" href="#main">Skip to result</a>
<header class="site-header"><a class="brand" href="#main" aria-label="HEPLab home"><svg class="brand-mark" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" stroke-width="5"/><path d="M9 32h46M32 9v46" stroke="currentColor" stroke-width="4"/></svg><span>HEPLab</span></a><nav class="site-nav" aria-label="Main"><span>Get started</span><span>Education</span><span>Gallery</span></nav><div class="site-actions"><span class="top-link">GitHub</span><select class="theme-select" id="theme-select" aria-label="Select theme"><option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option></select></div></header>
<div class="doc-layout"><aside class="sidebar" aria-label="HEPLab navigation"><section class="nav-group"><h2 class="nav-heading">Start here</h2><nav class="nav-list"><span>HEPLab overview</span><span>Getting started</span></nav></section><section class="nav-group"><h2 class="nav-heading">Use HEPLab</h2><nav class="nav-list"><span>Local workbench</span><span>Analysis workflow</span><span>Rediscover the Z boson</span><span>Results gallery</span></nav></section><section class="nav-group"><h2 class="nav-heading">Reference</h2><nav class="nav-list"><span>Python API v1</span><span>Validation evidence</span></nav></section></aside>
<main id="main" class="result-content" tabindex="-1">
<section class="page-heading"><div class="eyebrow" id="result-kind"></div><h1>__TITLE__</h1><p id="subtitle"></p><span class="result-tag">Provenance attached</span></section>
<div id="views"></div>
<section class="panel" id="provenance-panel"><details><summary>Run provenance</summary><div id="provenance"></div></details></section>
<section class="panel" id="record-panel"><details><summary>Full result record (JSON)</summary><pre id="raw"></pre></details></section>
<footer class="gallery-footer"><span>HEPLab · Reproducible results with declared limits</span><span>Result digest: <code id="digest"></code></span></footer>
<div class="tip" id="tip"></div></main><aside class="toc" aria-label="On this page"><p>On this page</p><nav class="nav-list"><a href="#main">Overview</a><a href="#views">Result plots and cutflow</a><a href="#provenance-panel">Run provenance</a><a href="#record-panel">Full result record</a></nav><p style="margin-top:1.25rem">One file · Works offline</p></aside></div>
<script type="application/json" id="heplab-meta">__META__</script>
<script type="application/json" id="heplab-data">__DATA__</script>
<script>__SCRIPT__</script><script>(()=>{const select=document.getElementById('theme-select'),key='heplab-export-theme';let saved='auto';try{saved=localStorage.getItem(key)||'auto'}catch{}select.value=saved;if(saved!=='auto')document.documentElement.dataset.theme=saved;select.addEventListener('change',()=>{try{localStorage.setItem(key,select.value)}catch{}if(select.value==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=select.value})})()</script>
</body></html>
"""

GALLERY = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='27' fill='%232f6fb0'/%3E%3Cpath d='M12 32h40M32 12v40' stroke='white' stroke-width='4'/%3E%3C/svg%3E"><style>__STYLE__</style></head>
<body><main class="gallery-shell"><header class="topbar"><span class="brand">HEPLab <span style="color:#91aaad;font-weight:500">/ Public examples</span></span><span class="muted">Static · No uploads · No tracking</span></header>
<section class="gallery-hero"><div><div class="eyebrow">A small gallery of reproducible results</div><h1>Read the shape of an event.</h1><p>Open a result, inspect the plot, and follow its provenance. These examples show how HEPLab packages an analysis; the data are synthetic teaching fixtures, not CMS measurements.</p></div><aside class="hero-note"><strong>__COUNT__ examples</strong><br/>Each result is a self-contained offline page with an embedded record and digest.</aside></section>
<div class="filter-row" role="group" aria-label="Filter examples"><span>Explore</span><button type="button" data-filter="all" aria-pressed="true">All results</button><button type="button" data-filter="analysis" aria-pressed="false">Mass analyses</button><button type="button" data-filter="event" aria-pressed="false">Event displays</button></div>
<section class="gallery-grid" id="gallery-grid">__CARDS__</section>
<footer class="gallery-footer"><span>Examples are synthetic and for teaching.</span><span>Want to publish your own? Export a result locally with <code>heplab export-html</code>.</span></footer></main>
<script>document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{const filter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));document.querySelectorAll('.gallery-card').forEach(card=>card.hidden=filter!=='all'&&card.dataset.kind!==filter);}));</script>
</body></html>
"""

SCRIPT = r"""
(()=>{
const meta=JSON.parse(document.getElementById('heplab-meta').textContent);
const data=JSON.parse(document.getElementById('heplab-data').textContent);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const tip=document.getElementById('tip');
const el=(tag,attrs={},...kids)=>{const e=document.createElement(tag);
  for(const[k,v]of Object.entries(attrs))k==='text'?e.textContent=v:e.setAttribute(k,v);
  e.append(...kids);return e;};
const fmt=v=>typeof v==='number'?(Math.abs(v)>=1e4||(v!==0&&Math.abs(v)<1e-3)?v.toExponential(3):+v.toFixed(4)):String(v);
document.getElementById('result-kind').textContent=`${meta.kind} · ${data.data_kind||'declared sample'}`;
document.getElementById('subtitle').textContent=
  `${meta.kind} · result ${String(meta.result_sha256).slice(0,16)} · HEPLab ${meta.heplab_version} · exported ${meta.exported_utc}`;
document.getElementById('digest').textContent=String(meta.result_sha256);
document.getElementById('raw').textContent=JSON.stringify(data,null,2);
const views=document.getElementById('views');

function canvas(height=320){const c=el('canvas');c.style.height=height+'px';return c;}
function fit(c){const r=c.getBoundingClientRect(),d=devicePixelRatio||1;
  c.width=Math.max(1,r.width*d);c.height=Math.max(1,r.height*d);const g=c.getContext('2d');g.setTransform(d,0,0,d,0,0);return[g,r.width,r.height];}
function showTip(ev,text){tip.textContent=text;tip.style.display='block';
  tip.style.left=Math.min(ev.clientX+12,innerWidth-200)+'px';tip.style.top=(ev.clientY+12)+'px';}
const hideTip=()=>{tip.style.display='none';};

function histogram(h){
  const panel=el('section',{class:'panel'});
  const log=el('button',{type:'button','aria-pressed':'false',text:'Log scale'});
  const zoomIn=el('button',{type:'button',text:'Zoom in'}),zoomOut=el('button',{type:'button',text:'Zoom out'});
  const reset=el('button',{type:'button',text:'Reset zoom'});
  panel.append(el('h2',{text:`${h.observable||'observable'} (${h.units||''})`}),
    el('div',{class:'bar'},zoomIn,zoomOut,log,reset,el('span',{class:'muted',text:'Drag or use zoom buttons. Focus the plot and use +/−, arrows, or Home.'})));
  const c=canvas();c.tabIndex=0;c.setAttribute('role','img');c.setAttribute('aria-label',`${h.observable||'Observable'} histogram. Use zoom buttons or keyboard controls.`);panel.append(c);views.append(panel);
  const edges=h.edges,counts=h.counts,err=(h.sumw2||counts).map(v=>Math.sqrt(Math.max(0,v)));
  let lo=edges[0],hi=edges.at(-1),useLog=false,drag=null;
  const L=48,R=12,T=10,B=34;
  // Map from the canvas's current size on every use, so hover and zoom stay
  // right even between a resize and the next redraw.
  const inv=px=>lo+(px-L)/(c.getBoundingClientRect().width-L-R)*(hi-lo);
  function draw(){
    const[g,w,ht]=fit(c),pw=w-L-R,ph=ht-T-B;
    const idx=counts.map((_,i)=>i).filter(i=>edges[i+1]>lo&&edges[i]<hi);
    const top=Math.max(1,...idx.map(i=>counts[i]+err[i]))*1.08;
    const y=v=>useLog?T+ph-ph*Math.log10(Math.max(v,0.5)/0.5)/Math.log10(top/0.5):T+ph-ph*v/top;
    const x=v=>L+pw*(v-lo)/(hi-lo);
    g.clearRect(0,0,w,ht);g.font='11px system-ui';g.fillStyle=css('--muted');g.strokeStyle=css('--grid');
    for(let k=0;k<=4;k++){const v=useLog?0.5*Math.pow(top/0.5,k/4):top*k/4,py=y(v);
      g.beginPath();g.moveTo(L,py);g.lineTo(w-R,py);g.stroke();g.fillText(fmt(Math.round(v)),4,py+4);}
    for(let k=0;k<=5;k++){const v=lo+(hi-lo)*k/5;g.fillText(fmt(+v.toFixed(1)),x(v)-10,ht-B+16);}
    g.fillText(`${h.observable||''} [${h.units||''}]`,L+pw/2-40,ht-4);
    g.fillStyle=css('--accent');g.globalAlpha=.8;
    for(const i of idx){const a=x(Math.max(edges[i],lo)),b=x(Math.min(edges[i+1],hi)),py=y(counts[i]);
      g.fillRect(a,py,Math.max(1,b-a-1),T+ph-py);}
    g.globalAlpha=1;g.strokeStyle=css('--ink');
    for(const i of idx){if(!counts[i])continue;const cx=x((edges[i]+edges[i+1])/2);
      g.beginPath();g.moveTo(cx,y(counts[i]+err[i]));g.lineTo(cx,y(Math.max(counts[i]-err[i],useLog?.5:0)));g.stroke();}
    if(drag){g.fillStyle=css('--accent-2');g.globalAlpha=.2;g.fillRect(Math.min(drag.a,drag.b),T,Math.abs(drag.b-drag.a),ph);g.globalAlpha=1;}
  }
  const at=ev=>ev.clientX-c.getBoundingClientRect().left;
  c.onpointerdown=ev=>{drag={a:at(ev),b:at(ev)};c.setPointerCapture(ev.pointerId);};
  c.onpointermove=ev=>{if(drag){drag.b=at(ev);draw();return;}
    const v=inv(at(ev)),i=edges.findIndex((e,k)=>k<counts.length&&v>=e&&v<edges[k+1]);
    if(i<0)return hideTip();showTip(ev,`[${fmt(edges[i])}, ${fmt(edges[i+1])}) ${h.units||''}: ${fmt(counts[i])} ± ${fmt(err[i])}`);};
  c.onpointerleave=hideTip;
  c.onpointerup=()=>{if(drag&&Math.abs(drag.b-drag.a)>6){const a=inv(Math.min(drag.a,drag.b)),b=inv(Math.max(drag.a,drag.b));
    lo=Math.max(edges[0],a);hi=Math.min(edges.at(-1),b);}drag=null;draw();};
  log.onclick=()=>{useLog=!useLog;log.setAttribute('aria-pressed',useLog);draw();};
  const zoom=f=>{const mid=(lo+hi)/2,half=(hi-lo)*f/2;lo=Math.max(edges[0],mid-half);hi=Math.min(edges.at(-1),mid+half);draw();};
  zoomIn.onclick=()=>zoom(.7);zoomOut.onclick=()=>zoom(1/.7);
  reset.onclick=()=>{lo=edges[0];hi=edges.at(-1);draw();};
  c.onkeydown=ev=>{if(ev.key==='+'||ev.key==='='){ev.preventDefault();zoom(.7);}else if(ev.key==='-'){ev.preventDefault();zoom(1/.7);}
    else if(ev.key==='Home'){ev.preventDefault();reset.click();}else if(ev.key==='ArrowLeft'||ev.key==='ArrowRight'){ev.preventDefault();const shift=(hi-lo)*.1*(ev.key==='ArrowLeft'?-1:1);lo=Math.max(edges[0],lo+shift);hi=Math.min(edges.at(-1),hi+shift);draw();}};
  const rows=counts.slice(0,5000).map((v,i)=>el('tr',{},el('td',{text:`${fmt(edges[i])}–${fmt(edges[i+1])} ${h.units||''}`}),el('td',{class:'num',text:fmt(v)}),el('td',{class:'num',text:fmt(err[i])})));
  const bins=el('details',{},el('summary',{text:'Accessible histogram data'}));const table=el('table');table.append(el('tr',{},el('th',{text:'Bin range'}),el('th',{text:'Count'}),el('th',{text:'Uncertainty'})),...rows);bins.append(table);panel.append(bins);
  if(counts.length>5000)bins.append(el('p',{class:'muted',text:'Showing the first 5,000 bins. Use the embedded result JSON for the complete histogram.'}));
  draw();new ResizeObserver(draw).observe(c);
}

function cutflow(result){
  const flow=result.cutflow||{},weighted=result.cutflow_weighted||{};
  const table=el('table');table.append(el('tr',{},el('th',{text:'Stage'}),el('th',{text:'Events'}),el('th',{text:'Σw ± stat.'}),el('th',{text:'of previous'})));
  let previous=null;
  const order=['all','certified','trigger','at_least_two_muons','selected_muons','opposite_charge_pair','mass_window'];
  const stages=[...order.filter(stage=>stage in flow),...Object.keys(flow).filter(stage=>!order.includes(stage))];
  for(const stage of stages){const count=flow[stage];
    const share=previous?`${(100*count/previous).toFixed(1)} %`:'';
    const w=weighted[stage],sumw=w&&typeof w==='object'?`${fmt(w.sumw)} ± ${fmt(Math.sqrt(Math.max(0,w.sumw2||0)))}`:fmt(w);
    table.append(el('tr',{},el('td',{text:stage}),el('td',{class:'num',text:fmt(count)}),
      el('td',{class:'num',text:stage in weighted?sumw:''}),el('td',{class:'num',text:share})));
    previous=count||previous;
  }
  return el('section',{class:'panel'},el('h2',{text:'Cutflow'}),table);
}

function eventDisplay(result){
  const panel=el('section',{class:'panel'});
  panel.append(el('h2',{text:'Event display'}),el('p',{class:'muted',text:'A synthetic angular muon pair propagated in the CMS tracker field model. Detector module lines and envelopes come from pinned CMS display meshes for visualization only; tracks stop at the field model validity boundary. Use tracker focus to inspect curvature or full-detector scale for the complete layout.'}));
  const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let progress=reducedMotion?1:0,playing=!reducedMotion,lastFrame=0,frame=0;
  const painters=[];
  const play=el('button',{type:'button',text:playing?'Pause':'Play animation'});
  const replay=el('button',{type:'button',text:'Replay'});
  const scrub=el('input',{type:'range',min:'0',max:'100',step:'1',value:String(Math.round(progress*100)),'aria-label':'Event animation progress'});
  scrub.className='event-scrubber';
  const scaleSelect=el('select',{class:'theme-select','aria-label':'Detector scale'});
  scaleSelect.append(el('option',{value:'tracker',text:'Tracker focus'}),el('option',{value:'full',text:'Full detector'}));
  const status=el('span',{class:'muted','aria-live':'polite',text:reducedMotion?'Animation ready. Press play to view the event.':'Particles emerge from the collision…'});
  panel.append(el('div',{class:'bar event-controls'},play,replay,el('label',{class:'event-scrub-label'},el('span',{text:'Progress'}),scrub),scaleSelect,status));
  const grid=el('div',{class:'grid'}),views2=[canvas(360),canvas(360)];views2.forEach((c,i)=>{c.tabIndex=0;c.setAttribute('role','img');c.setAttribute('aria-label',`${i?'Longitudinal z-r':'Transverse x-y'} event view. Use zoom buttons or keyboard controls.`);});grid.append(...views2);panel.append(grid);views.append(panel);
  const surfaces=(result.geometry&&result.geometry.surfaces)||[];
  const tracks=result.tracks.map(t=>({t,points:(t.trajectory&&t.trajectory.points)||t.points||[]}));
  const cmsLayers=result.cms_display_geometry?.layers||[];
  const detectorRadius=Math.max(.2,...surfaces.map(s=>s.radius_m||s.outer_radius_m||s.inner_radius_m||0),...cmsLayers.map(layer=>layer.max_radius_m||0));
  const detectorHalfLength=Math.max(detectorRadius,...surfaces.map(s=>s.half_length_m||Math.abs(s.z_m||0)),...cmsLayers.map(layer=>Math.max(Math.abs(layer.min_z_m||0),Math.abs(layer.max_z_m||0))));
  const trackerRadius=Math.max(1.2,...surfaces.filter(s=>s.subsystem!=='solenoid').map(s=>s.radius_m||s.outer_radius_m||s.inner_radius_m||0),...cmsLayers.filter(layer=>['pixel','strips'].includes(layer.id)).map(layer=>layer.max_radius_m||0));
  const trackerHalfLength=Math.max(2.8,...surfaces.filter(s=>s.subsystem!=='solenoid').map(s=>s.half_length_m||Math.abs(s.z_m||0)),...cmsLayers.filter(layer=>['pixel','strips'].includes(layer.id)).map(layer=>Math.max(Math.abs(layer.min_z_m||0),Math.abs(layer.max_z_m||0))));
  let fullDetector=false;
  const layerColor={pixel:'--detector-pixel',strips:'--detector-tracker',ecal:'--detector-ecal',hcal:'--detector-hcal',dt:'--detector-muon',csc:'--detector-muon',rpc:'--detector-muon'};
  const project=[p=>[p[0],p[1]],p=>[p[2],Math.hypot(p[0],p[1])]];
  const legend=el('div',{class:'event-legend','aria-label':'Detector and track legend'},
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch pixel'}),el('span',{text:'Pixel'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch tracker'}),el('span',{text:'Silicon tracker'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch ecal'}),el('span',{text:'ECAL'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch hcal'}),el('span',{text:'HCAL'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch muon'}),el('span',{text:'Muon chambers'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch solenoid'}),el('span',{text:'Solenoid bore'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch charge-positive'}),el('span',{text:'q +1'})),
    el('span',{class:'event-legend-item'},el('i',{class:'event-swatch charge-negative'}),el('span',{text:'q −1'})));
  panel.insertBefore(legend,grid);
  views2.forEach((c,view)=>{
    let scale=1,ox=0,oy=0,pan=null,hit=[];
    const meshCanvas=document.createElement('canvas');let meshCacheKey='';
    const zoomIn=el('button',{type:'button',text:'Zoom in'}),zoomOut=el('button',{type:'button',text:'Zoom out'}),reset=el('button',{type:'button',text:'Reset view'});
    panel.insertBefore(el('div',{class:'bar'},el('strong',{text:view?'Longitudinal view':'Transverse view'}),zoomIn,zoomOut,reset),grid);
    function draw(){
      const outerRadius=fullDetector?detectorRadius:trackerRadius,outerZ=fullDetector?detectorHalfLength:trackerHalfLength;
      const[g,w,h]=fit(c),extent=view?Math.max(outerZ,outerRadius):outerRadius,s=scale*Math.min(w,h)/(2.15*extent),cx=w/2+ox,cy=h/2+oy;
      const P=([a,b])=>[cx+a*s,cy-b*s];g.clearRect(0,0,w,h);g.lineWidth=1;g.strokeStyle=css('--grid');
      const cacheKey=[w,h,s,cx,cy,...Object.values(layerColor).map(css)].join(':');
      if(meshCacheKey!==cacheKey){
        meshCanvas.width=Math.max(1,Math.round(w));meshCanvas.height=Math.max(1,Math.round(h));
        const mesh=meshCanvas.getContext('2d');mesh.clearRect(0,0,w,h);mesh.lineWidth=.65;mesh.globalAlpha=.4;
        for(const layer of cmsLayers){const values=view?layer.zr_lines:layer.xy_lines;if(!values?.length)continue;
          mesh.strokeStyle=css(layerColor[layer.id]||'--detector-tracker');mesh.beginPath();
          for(let index=0;index+3<values.length;index+=4){const [x0,y0]=P([values[index],values[index+1]]),[x1,y1]=P([values[index+2],values[index+3]]);mesh.moveTo(x0,y0);mesh.lineTo(x1,y1);}
          mesh.stroke();
        }
        meshCacheKey=cacheKey;
      }
      g.drawImage(meshCanvas,0,0,w,h);
      for(const sf of surfaces){
        const color=sf.subsystem==='pixel'?css('--detector-pixel'):sf.subsystem==='solenoid'?css('--detector-solenoid'):css('--detector-tracker');
        g.strokeStyle=color;g.globalAlpha=.78;g.lineWidth=sf.subsystem==='pixel'?1:1.5;
        if(view===0&&sf.kind==='cylinder'&&sf.radius_m){g.beginPath();g.arc(cx,cy,sf.radius_m*s,0,2*Math.PI);g.stroke();}
        else if(view===0&&sf.kind==='disk'){
          for(const radius of[sf.inner_radius_m,sf.outer_radius_m])if(radius){g.beginPath();g.arc(cx,cy,radius*s,0,2*Math.PI);g.stroke();}
        }else if(view===1&&sf.kind==='cylinder'&&sf.radius_m){
          const z=Math.min(sf.half_length_m||detectorHalfLength,detectorHalfLength),r=sf.radius_m;
          g.beginPath();g.moveTo(cx-z*s,cy-r*s);g.lineTo(cx+z*s,cy-r*s);g.stroke();
        }else if(view===1&&sf.kind==='disk'){
          const z=sf.z_m||0;g.beginPath();g.moveTo(cx+z*s,cy-(sf.inner_radius_m||0)*s);g.lineTo(cx+z*s,cy-(sf.outer_radius_m||0)*s);g.stroke();
        }
      }
      for(const layer of cmsLayers){
        const color=css(layerColor[layer.id]||'--detector-tracker');g.strokeStyle=color;g.fillStyle=color;g.lineWidth=1;g.globalAlpha=.72;
        if(view===0){g.beginPath();g.arc(cx,cy,(layer.max_radius_m||0)*s,0,2*Math.PI);g.stroke();}
        else{
          const left=cx+(layer.min_z_m||0)*s,right=cx+(layer.max_z_m||0)*s;
          const top=cy-(layer.max_radius_m||0)*s,bottom=cy-(layer.min_radius_m||0)*s;
          g.globalAlpha=.1;g.fillRect(left,top,right-left,bottom-top);g.globalAlpha=.82;g.strokeRect(left,top,right-left,bottom-top);
        }
      }
      g.globalAlpha=1;g.setLineDash([3,5]);g.strokeStyle=css('--grid');g.lineWidth=1;g.beginPath();
      if(view===0){g.moveTo(cx-w/2,cy);g.lineTo(cx+w/2,cy);g.moveTo(cx,cy-h/2);g.lineTo(cx,cy+h/2);}
      else{g.moveTo(cx-w/2,cy);g.lineTo(cx+w/2,cy);}
      g.stroke();g.setLineDash([]);
      hit=[];tracks.forEach(({t,points},i)=>{if(points.length<2)return;
        const visible=[];for(const point of points){const [a,b]=project[view](point),inside=view===0?Math.hypot(a,b)<=detectorRadius:Math.abs(a)<=detectorHalfLength&&b<=detectorRadius;if(!inside)break;visible.push(point);}
        if(visible.length<2)return;
        const line=visible.map(point=>P(project[view](point)));
        const lengths=line.slice(1).map((point,index)=>Math.hypot(point[0]-line[index][0],point[1]-line[index][1]));
        const total=lengths.reduce((sum,length)=>sum+length,0),remaining=total*progress;
        const color=t.charge>0?css('--accent-2'):css('--accent');
        g.save();g.strokeStyle=css('--grid');g.lineWidth=1.5;g.setLineDash([3,5]);g.beginPath();
        line.forEach(([x,y],index)=>index?g.lineTo(x,y):g.moveTo(x,y));g.stroke();g.restore();
        let distance=remaining,marker=line[0];g.strokeStyle=color;g.lineWidth=2.5;g.lineCap='round';g.lineJoin='round';g.beginPath();g.moveTo(line[0][0],line[0][1]);
        hit.push([line[0][0],line[0][1],i]);
        for(let segment=0;segment<lengths.length&&distance>0;segment++){
          const start=line[segment],end=line[segment+1],length=lengths[segment],fraction=Math.min(1,distance/Math.max(length,1e-9));
          marker=[start[0]+(end[0]-start[0])*fraction,start[1]+(end[1]-start[1])*fraction];
          g.lineTo(marker[0],marker[1]);hit.push([marker[0],marker[1],i]);distance-=length;
          if(fraction<1)break;
        }
        g.stroke();
        if(progress>0){g.save();g.shadowColor=color;g.shadowBlur=14;g.fillStyle=color;g.beginPath();g.arc(marker[0],marker[1],4.5,0,2*Math.PI);g.fill();g.restore();}
      });
      const pulse=2+1.5*(.5+.5*Math.sin(progress*Math.PI*10));g.fillStyle=css('--accent');g.globalAlpha=.55;g.beginPath();g.arc(cx,cy,pulse,0,2*Math.PI);g.fill();g.globalAlpha=1;
      g.fillStyle=css('--muted');g.font='11px system-ui';g.fillText(view?'z (m)':'x (m)',w-42,h-7);g.fillText(view?'r (m)':'y (m)',8,16);
    }
    c.onwheel=ev=>{ev.preventDefault();scale*=ev.deltaY<0?1.15:1/1.15;draw();};
    zoomIn.onclick=()=>{scale*=1.2;draw();};zoomOut.onclick=()=>{scale/=1.2;draw();};reset.onclick=()=>{scale=1;ox=oy=0;draw();};
    c.onkeydown=ev=>{if(ev.key==='+'||ev.key==='='){ev.preventDefault();zoomIn.click();}else if(ev.key==='-'){ev.preventDefault();zoomOut.click();}
      else if(ev.key==='Home'){ev.preventDefault();reset.click();}else if(ev.key.startsWith('Arrow')){ev.preventDefault();const d=24;if(ev.key==='ArrowLeft')ox+=d;if(ev.key==='ArrowRight')ox-=d;if(ev.key==='ArrowUp')oy+=d;if(ev.key==='ArrowDown')oy-=d;draw();}};
    c.onpointerdown=ev=>{pan=[ev.clientX-ox,ev.clientY-oy];c.setPointerCapture(ev.pointerId);};
    c.onpointerup=()=>{pan=null;};
    c.onpointermove=ev=>{if(pan){ox=ev.clientX-pan[0];oy=ev.clientY-pan[1];draw();return;}
      const r=c.getBoundingClientRect(),mx=ev.clientX-r.left,my=ev.clientY-r.top;
      let best=null,d=144;for(const[a,b,i]of hit){const q=(a-mx)**2+(b-my)**2;if(q<d){d=q;best=i;}}
      if(best===null)return hideTip();const t=tracks[best].t,m=(t.truth&&t.truth.momentum)||{};
      showTip(ev,`track ${t.object_id} · pdg ${t.pdg_id} · q=${t.charge} · |p|=${fmt(Math.hypot(m.px||0,m.py||0,m.pz||0))} GeV`);};
    c.onpointerleave=hideTip;painters.push(draw);new ResizeObserver(draw).observe(c);
  });
  const paint=()=>painters.forEach(draw=>draw());
  new MutationObserver(paint).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  scaleSelect.onchange=()=>{fullDetector=scaleSelect.value==='full';painters.forEach(draw=>draw());};
  const animate=now=>{if(!playing)return;if(!lastFrame)lastFrame=now;progress=Math.min(1,progress+(now-lastFrame)/3400);lastFrame=now;scrub.value=String(Math.round(progress*100));paint();
    if(progress<1)frame=requestAnimationFrame(animate);else{playing=false;play.textContent='Play animation';status.textContent='Event complete. Replay or scrub to inspect the tracks.';}};
  const stop=()=>{playing=false;lastFrame=0;if(frame)cancelAnimationFrame(frame);play.textContent='Play animation';};
  play.onclick=()=>{if(playing){stop();status.textContent='Paused. Resume or scrub through the event.';return;}if(progress>=1)progress=0;playing=true;lastFrame=0;play.textContent='Pause';status.textContent='Particles are crossing the detector…';frame=requestAnimationFrame(animate);};
  replay.onclick=()=>{stop();progress=0;scrub.value='0';paint();playing=true;play.textContent='Pause';status.textContent='Particles emerge from the collision…';frame=requestAnimationFrame(animate);};
  scrub.oninput=()=>{stop();progress=Number(scrub.value)/100;paint();status.textContent=progress===1?'Event complete.':'Scrubbing through the detector…';};
  paint();if(playing)frame=requestAnimationFrame(animate);
  const trackTable=el('table');trackTable.append(el('tr',{},el('th',{text:'Track'}),el('th',{text:'PDG ID'}),el('th',{text:'Charge'}),el('th',{text:'Momentum (GeV)'})));
  for(const {t} of tracks){const m=(t.truth&&t.truth.momentum)||{};trackTable.append(el('tr',{},el('td',{text:String(t.object_id)}),el('td',{text:String(t.pdg_id)}),el('td',{text:String(t.charge)}),el('td',{text:fmt(Math.hypot(m.px||0,m.py||0,m.pz||0))})));}
  panel.append(el('details',{},el('summary',{text:'Track data for screen readers'}),trackTable));
}

function lifetimeView(result){
  const summary=result.summary||{},config=result.config||{};
  const panel=el('section',{class:'panel'});
  panel.append(el('h2',{text:'Fixed-momentum muon survival'}));
  panel.append(el('p',{text:'Expected survival follows the proper-time exponential. The seeded sample is a reproducibility check; it is not detector or atmospheric-shower validation.'}));
  const table=el('table');
  const rows=[
    ['Momentum',`${fmt(config.momentum_gev_c)} GeV/c`],
    ['Flight path',`${fmt(config.path_length_m)} m`],
    ['Mean decay path',`${fmt(summary.mean_decay_path_m)} m`],
    ['Expected survival',`${fmt(summary.expected_survival_probability)} (analytic)`],
    ['Observed survival',`${fmt(summary.observed_survival_probability)} (${summary.observed_survivors}/${config.sample_size})`],
    ['95% Wilson interval',JSON.stringify(summary.survival_wilson_95_percent||[])],
    ['Seed',String(config.seed)],
    ['RNG version',String(config.rng_version||'not recorded')]
  ];
  for(const [name,value]of rows)table.append(el('tr',{},el('th',{scope:'row',text:name}),el('td',{text:value})));
  panel.append(table);
  const comparison=el('div',{class:'survival-comparison'});
  for(const [label,value]of [['Analytic expectation',summary.expected_survival_probability],['Seeded sample',summary.observed_survival_probability]]){
    const row=el('div',{class:'survival-row'});row.append(el('span',{text:label}));
    const progress=el('progress',{max:'1',value:String(value??0),'aria-label':label});
    row.append(progress,el('code',{text:fmt(value??0)}));comparison.append(row);
  }
  panel.append(comparison);
  panel.append(el('p',{class:'muted',text:'Model limits: constant momentum, straight flight, vacuum decay law. No production spectrum, air energy loss, scattering, shower, or decay daughters are simulated.'}));
  document.getElementById('views').append(panel);
}

function provenance(result){
  const rows=[];const add=(k,v)=>{if(v!==undefined&&v!==null&&v!=='')rows.push([k,typeof v==='object'?JSON.stringify(v):String(v)]);};
  const p=result.provenance||{};for(const[k,v]of Object.entries(p))add(k,v);
  if(meta.manifest)add('heplab-share-v2 manifest',meta.manifest);
  if(result.cms_display_geometry){const g=result.cms_display_geometry;add('display_geometry_source',`${g.source}@${g.commit} (${g.license})`);add('display_geometry_scope',g.scope);}
  for(const k of['analysis','analysis_config_sha256','result_sha256','payload_content_sha256','data_kind','created_at'])add(k,result[k]);
  if(result.artifact)for(const[k,v]of Object.entries(result.artifact))add('artifact.'+k,v);
  if(result.config)add('config',result.config);if(result.validation)add('validation',result.validation);
  const table=el('table');for(const[k,v]of rows)table.append(el('tr',{},el('td',{text:k}),el('td',{},el('code',{text:v}))));
  document.getElementById('provenance').append(rows.length?table:el('p',{class:'muted',text:'This result carries no provenance record.'}));
}

if(meta.kind==='analysis'){histogram(data.histogram);views.append(cutflow(data));}
else if(meta.kind==='lifetime')lifetimeView(data);
else eventDisplay(data);
provenance(data);
})();
"""
