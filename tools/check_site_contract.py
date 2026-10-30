"""Check the canonical ASP.NET guide's route and authored-source contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "web/HEPLab.Web"
DOCS = SITE / "Content/Docs"


def main() -> int:
    service = (SITE / "Services/SiteContentService.cs").read_text(encoding="utf-8")
    razor = (SITE / "Pages/Docs.cshtml").read_text(encoding="utf-8")
    model = (SITE / "Pages/Docs.cshtml.cs").read_text(encoding="utf-8")

    routes = re.findall(r'new\("[^"]+",\s*"([^\"]+)"\)', service)
    missing = []
    for route in routes:
        if route == "/":
            continue
        relative = route.strip("/")
        suffix = ".mdx" if relative in {"education", "gallery", "results"} else ".md"
        if not (DOCS / (relative + suffix)).is_file():
            missing.append(route)
    if missing:
        raise SystemExit(f"navigation routes without canonical source pages: {missing}")

    source_prefix = "web/HEPLab.Web/Content/Docs/"
    if source_prefix not in razor or "web/Content/Docs/" in razor:
        raise SystemExit("edit-page source path does not match the canonical web tree")
    if "SourcePath = Doc.Url.Trim('/') + \".md\"" not in model:
        raise SystemExit("Markdown page source mapping is missing")
    if any(
        f'SourcePath = "{name}.mdx"' not in model for name in ("education", "gallery", "results")
    ):
        raise SystemExit("MDX source mapping is missing")
    if ".DisableHtml()" not in service:
        raise SystemExit("authored HTML must be escaped by the Markdown pipeline")

    pages = list(DOCS.rglob("*.md")) + list(DOCS.rglob("*.mdx"))
    bad_local_routes = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for target in re.findall(r"\]\((/[^)#?]+/?)(?:#[^)]*)?\)", text):
            route = target if target.endswith("/") else target + "/"
            if route == "/":
                continue
            relative = route.strip("/")
            suffix = ".mdx" if relative in {"education", "gallery", "results"} else ".md"
            if (
                not (DOCS / (relative + suffix)).is_file()
                and not (SITE / "wwwroot" / target.lstrip("/")).is_file()
            ):
                bad_local_routes.append((page.relative_to(DOCS).as_posix(), target))
    if bad_local_routes:
        raise SystemExit(f"broken local guide links: {bad_local_routes}")

    examples = SITE / "wwwroot/examples"
    expected_examples = {
        "analytic-muon-pair-event.html",
        "analytic-muon-pair-config-v2.json",
        "analytic-muon-pair-result-v1.json",
        "pdg-silicon-mean-loss.html",
        "cms-resonance-reference-regression-v2.html",
        "cms-resonance-data-report-v2.json",
        "curvature-sagitta-sweep-v1.html",
        "curvature-sweep-v1.json",
    }
    missing_examples = sorted(name for name in expected_examples if not (examples / name).is_file())
    if missing_examples:
        raise SystemExit(f"gallery evidence examples are missing: {missing_examples}")
    pdg_example = (examples / "pdg-silicon-mean-loss.html").read_text(encoding="utf-8")
    cms_example = (examples / "cms-resonance-reference-regression-v2.html").read_text(
        encoding="utf-8"
    )
    if "PDG 2025 reference-table reproduction" not in pdg_example:
        raise SystemExit("PDG example is missing its evidence classification")
    if "gate: FAILED" not in cms_example or "not an independent dataset" not in cms_example:
        raise SystemExit("CMS example must expose the failed gate and same-file holdout scope")
    if "/../src/heplab/" in cms_example:
        raise SystemExit(
            "CMS example contains a repository-relative source link that cannot resolve"
        )
    curvature_example = (examples / "curvature-sagitta-sweep-v1.html").read_text(encoding="utf-8")
    if (
        "Synthetic equation/model comparison" not in curvature_example
        or "no field-measurement acceptance threshold" not in curvature_example
        or "curvature-sweep-v1.json" not in curvature_example
    ):
        raise SystemExit(
            "curvature example must expose its model scope, limits, and versioned report"
        )
    setup_path = examples / "analytic-muon-pair-config-v2.json"
    result_path = examples / "analytic-muon-pair-result-v1.json"
    if not setup_path.is_file() or not result_path.is_file():
        raise SystemExit("guided Workbench experiment must ship its setup and result downloads")
    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if setup.get("schema") != "heplab-run-config-v2":
        raise SystemExit("guided Workbench setup is not a grouped v2 configuration")
    if not result.get("fixture_scope", "").startswith("synthetic declared back-to-back"):
        raise SystemExit("guided Workbench result must be visibly marked synthetic")
    if result.get("artifact", {}).get("schema") != "heplab-run-artifact-v1":
        raise SystemExit("guided Workbench result lacks a versioned full-run artifact")
    gallery = (SITE / "Pages/Shared/_ResultGallery.cshtml").read_text(encoding="utf-8")
    broken_gallery_links = []
    for target in re.findall(r'href="(/[^"#?]+)', gallery):
        if target.endswith("/"):
            relative = target.strip("/")
            suffix = ".mdx" if relative in {"education", "gallery", "results"} else ".md"
            if (DOCS / (relative + suffix)).is_file():
                continue
        elif (SITE / "wwwroot" / target.lstrip("/")).is_file():
            continue
        broken_gallery_links.append(target)
    if broken_gallery_links:
        raise SystemExit(
            f"gallery card links do not resolve in the active site: {broken_gallery_links}"
        )

    print(
        f"Site contract passed: {len(routes)} navigation entries, {len(pages)} source pages; "
        "canonical source links, generated evidence examples, a synthetic Workbench fixture, "
        "and raw-HTML policy are present."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
