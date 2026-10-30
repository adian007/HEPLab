"""Build provenance-bearing static examples for the canonical ASP.NET site."""

# Generated HTML fragments intentionally retain long source lines as HTML templates.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src/heplab/data/reference"
OUTPUT = ROOT / "web/HEPLab.Web/wwwroot/examples"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def page(title: str, eyebrow: str, body: str, source: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{esc(title)} · HEPLab example</title>
  <style>
    :root {{ color-scheme: light dark; font: 16px/1.55 system-ui, sans-serif; }}
    body {{ max-width: 920px; margin: 0 auto; padding: 2rem 1.2rem 4rem; }}
    main {{ display: grid; gap: 1rem; }}
    .eyebrow {{ color: #187078; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }}
    .notice {{ border: 2px solid #a76200; border-radius: .65rem; padding: 1rem; }}
    .panel {{ border: 1px solid #8886; border-radius: .65rem; padding: 1rem; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
    th, td {{ text-align: right; padding: .4rem .55rem; border-bottom: 1px solid #8885; }}
    th:first-child, td:first-child {{ text-align: left; }}
    code {{ overflow-wrap: anywhere; }}
    a {{ color: #16707b; }}
    .back {{ display: inline-block; margin-bottom: 1.2rem; }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ scroll-behavior: auto !important; }} }}
  </style>
</head>
<body>
  <a class="back" href="/gallery/">← Back to the HEPLab examples gallery</a>
  <main>
    <header><div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(title)}</h1></header>
    {body}
    <section class="panel"><h2>Provenance and scope</h2>{source}</section>
    <p><a href="/validation/evidence/">Read how HEPLab classifies evidence</a> · <a href="/simulation/models/">Model definitions and limits</a></p>
  </main>
</body>
</html>
"""


def pdg_example() -> str:
    table_path = DATA / "silicon-muon.json"
    calibration_path = DATA / "silicon-calibration.json"
    table = json.loads(table_path.read_text(encoding="utf-8"))
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    rows = table["rows"]
    heldout = set(calibration["heldout_rows"])
    training = set(calibration["training_rows"])
    trs = []
    for i, row in enumerate(rows):
        role = (
            "Training knot"
            if i in training
            else "Held-out reference row"
            if i in heldout
            else "Unclassified"
        )
        trs.append(
            "<tr>"
            f"<td>{row['kinetic_gev']:.4g}</td>"
            f"<td>{row['ionization_gev_per_m']:.9g}</td>"
            f"<td>{esc(role)}</td></tr>"
        )
    body = f"""<section class="notice"><strong>Reference-table reproduction, not a detector measurement.</strong>
      This example reproduces PDG 2025 mean muon ionization stopping power in silicon. The held-out maximum absolute relative error is {calibration["max_abs_relative_error"]:.4%} against a predeclared 2% threshold. Radiative loss, event-by-event straggling, sensor response, and CMS calibration are not tested.</section>
    <section class="panel"><h2>Declared interpolation result</h2>
      <p>Fit scope: log-linear interpolation in kinetic energy using {len(training)} alternating training rows; {len(heldout)} rows are held out from the fit. Valid tabulated domain: {rows[0]["kinetic_gev"]:g} to {rows[-1]["kinetic_gev"]:g} GeV kinetic energy. Requests outside that range are rejected.</p>
      <p>Target quantity: mean ionization stopping power, GeV/m. It is not a stochastic single-particle loss distribution.</p>
      <details><summary>Show all source table rows</summary><table><thead><tr><th>Kinetic energy (GeV)</th><th>Mean ionization (GeV/m)</th><th>Use in reproduction</th></tr></thead><tbody>{"".join(trs)}</tbody></table></details>
    </section>"""
    source = f"""<ul>
      <li>Reference: <a href="{esc(table["source_url"])}">PDG 2025 muon energy loss in silicon</a>.</li>
      <li>Downloaded source SHA-256: <code>{esc(table["source_sha256"])}</code>.</li>
      <li>Checked-in parsed rows SHA-256: <code>{sha256(table_path)}</code>.</li>
      <li>Reproduction recipe SHA-256: <code>{sha256(calibration_path)}</code>; ID <code>{esc(calibration["id"])}</code>.</li>
      <li>Output generated from repository files by <code>python tools/build_site_examples.py</code>.</li>
    </ul>"""
    return page(
        "Mean muon energy loss in silicon", "PDG 2025 reference-table reproduction", body, source
    )


def cms_example() -> str:
    report_path = DATA / "cms-resonance-data-report-v2.json"
    pairs_path = DATA / "cms-resonance-selected-pairs-v2.json"
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    fits = report["fits"]
    rows = []
    for name, fit in (
        ("J/ψ", fits["jpsi"]),
        ("Υ(1S)", fits["upsilon_1s"]),
        ("Υ(2S)", fits["upsilon_2s"]),
        ("Υ(3S)", fits["upsilon_3s"]),
    ):
        heldout = fit["heldout_fit"]
        gate = fit["heldout_reference_gate"]
        rows.append(
            "<tr>"
            f"<td>{esc(name)}</td><td>{heldout['mean_gev']:.6f}</td>"
            f"<td>{gate['mass_residual_gev']:+.6f}</td><td>{gate['mass_tolerance_gev']:.3f}</td>"
            f"<td>{'PASS' if gate['passed'] else 'FAIL'}</td></tr>"
        )
    ups2 = fits["upsilon_2s"]["heldout_reference_gate"]
    source_file = report["source"]["url"]
    body = f"""<section class="notice"><strong>Recorded CMS Open Data regression; overall gate: FAILED.</strong>
      The low-mass candidate is chosen by maximum scalar pT sum and does not use a PDG target mass. Events are split by a deterministic run/lumi/event hash before mass fitting. This is a disjoint holdout from one Run2016G file, not an independent dataset, detector calibration, or validation of HEPLab's simulation.</section>
    <section class="panel"><h2>Frozen held-out peak checks</h2>
      <p>Candidate selection is independent of target resonance mass. The Υ(2S) held-out residual is {ups2["mass_residual_gev"]:+.6f} GeV against a predeclared ±{ups2["mass_tolerance_gev"]:.3f} GeV gate, so the report correctly fails overall.</p>
      <table><thead><tr><th>Sample</th><th>Held-out fitted mean (GeV)</th><th>Residual (GeV)</th><th>Allowed (GeV)</th><th>Gate</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
      <p>The fit uncertainty is a Gaussian Fisher approximation and omits background uncertainty. Trigger and offline kinematic selections define the sample acceptance; no trigger-object matching, acceptance correction, or per-muon momentum correction is applied.</p>
    </section>
    <section class="panel"><h2>Sample and split</h2><ul>
      <li>Recorded data: CMS Run2016G DoubleMuon NanoAOD; entries [{report["source"]["entry_start"]}, {report["source"]["entry_stop"]}) from one file.</li>
      <li>Selected opposite-charge muons: pT ≥ 2 GeV and |η| &lt; 2.4; one pair/event maximizing scalar pT sum.</li>
      <li>Split: <code>{esc(report["source"]["event_split_algorithm"])}</code>, held-out fraction {report["source"]["split_fraction_heldout"]:.0%}.</li>
      <li>Candidate pairs: J/ψ {report["source"]["trigger_counts_and_candidates"]["candidate_events"]["jpsi"]:,}; Υ {report["source"]["trigger_counts_and_candidates"]["candidate_events"]["upsilon"]:,}.</li>
    </ul></section>"""
    source = f"""<ul>
      <li>Original file: <a href="{esc(source_file)}">CERN Open Data NanoAOD</a>; record <a href="https://opendata.cern.ch/record/30522">30522</a>.</li>
      <li>Source file Adler-32: <code>{esc(report["source"]["source_adler32"])}</code> (verified during input retrieval).</li>
      <li>Dataset manifest SHA-256: <code>{esc(report["source"]["dataset_manifest_sha256"])}</code>.</li>
      <li>Selected-pair fixture SHA-256: <code>{sha256(pairs_path)}</code> (declared {esc(report["source"]["selected_pairs_sha256"])}).</li>
      <li>Report file SHA-256: <code>{sha256(report_path)}</code>; deterministic result digest <code>{esc(report["deterministic_result_sha256"])}</code>.</li>
      <li>Full scope, fit diagnostics, and known limitations: <a href="cms-resonance-data-report-v2.json">download the versioned report JSON</a> and read the <a href="/validation/evidence/">evidence guide</a>.</li>
    </ul>"""
    return page(
        "Low-mass resonance reference regression",
        "Recorded CMS Open Data · failed gate",
        body,
        source,
    )


def curvature_example() -> str:
    report_path = DATA / "curvature-sweep-v1.json"
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    result = report["result"]
    ideal_rows = []
    for row in result["ideal_uniform_field"]:
        radius = "straight" if row["radius_m"] is None else f"{row['radius_m']:.6g}"
        ideal_rows.append(
            "<tr>"
            f"<td>{row['momentum_gev_c']:g}</td><td>{row['charge_e']:+g}</td>"
            f"<td>{row['field_t']:g}</td><td>{radius}</td>"
            f"<td>{row['signed_sagitta_m']:+.9g}</td></tr>"
        )
    tracker_rows = []
    for row in result["tracker_oae_reference"]:
        tracker_rows.append(
            "<tr>"
            f"<td>{row['momentum_gev_c']:g}</td><td>{row['charge_e']:+g}</td>"
            f"<td>{row['signed_sagitta_m']:+.9g}</td>"
            f"<td>{row['difference_from_uniform_3_8t_endpoint_m']:.6g}</td>"
            f"<td>{row['actual_path_m']:.6g} · {esc(row['termination'])}</td></tr>"
        )
    body = f"""<section class="notice"><strong>Synthetic equation/model comparison; no measured tracks.</strong>
      Muons start at the origin along +x, with η = 0, and are propagated for {result["config"]["path_length_m"]:g} m in vacuum. The exact uniform-field rows span momentum, charge, and field strength. The separate OAE rows use the pinned tracker field function at nominal 3.8 T.</section>
    <section class="panel"><h2>Exact uniform-field sweep</h2>
      <p>The signed sagitta is the transverse midpoint's signed distance from the endpoint chord. Radius is <code>pT / (0.299792458 |q/e| |B|)</code>; zero field is straight.</p>
      <table><thead><tr><th>p (GeV/c)</th><th>q/e</th><th>B (T)</th><th>Radius (m)</th><th>Signed sagitta (m)</th></tr></thead><tbody>{"".join(ideal_rows)}</tbody></table>
    </section>
    <section class="panel"><h2>Bounded tracker-field comparison</h2>
      <p>OAE RK4 paths are compared with the exact uniform 3.8 T helix at the same input. Endpoint differences are reported as diagnostics and have no field-measurement acceptance threshold.</p>
      <table><thead><tr><th>p (GeV/c)</th><th>q/e</th><th>OAE sagitta (m)</th><th>Endpoint Δ vs uniform 3.8 T (m)</th><th>Actual path / stop</th></tr></thead><tbody>{"".join(tracker_rows)}</tbody></table>
    </section>
    <p>Both paths are software predictions. No material transport, scattering, decay, detector response, field measurement agreement, or run-era conditions are included.</p>"""
    hashes = "".join(
        f"<li><code>{esc(name)}</code> SHA-256 <code>{esc(value)}</code></li>"
        for name, value in report["source_sha256"].items()
    )
    source = f"""<ul>
      <li>Constants record: <code>{esc(report["constants"]["id"])}</code> · <a href="https://pdg.lbl.gov/2025/">PDG 2025</a>.</li>
      <li>Model ID: <code>{esc(result["model_id"])}</code>; inputs and all case results are in the <a href="curvature-sweep-v1.json">versioned JSON report</a>.</li>
      {hashes}
      <li>Report SHA-256: <code>{sha256(report_path)}</code>; output built with <code>python tools/build_site_examples.py</code>.</li>
    </ul>"""
    return page("Magnetic curvature and sagitta sweep", "Software model comparison", body, source)


def main() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_curvature_sweep.py")],
        cwd=ROOT,
        check=True,
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "pdg-silicon-mean-loss.html").write_text(
        pdg_example(), encoding="utf-8", newline="\n"
    )
    (OUTPUT / "cms-resonance-reference-regression-v2.html").write_text(
        cms_example(), encoding="utf-8", newline="\n"
    )
    report_path = DATA / "cms-resonance-data-report-v2.json"
    (OUTPUT / "cms-resonance-data-report-v2.json").write_bytes(report_path.read_bytes())
    (OUTPUT / "curvature-sagitta-sweep-v1.html").write_text(
        curvature_example(), encoding="utf-8", newline="\n"
    )
    (OUTPUT / "curvature-sweep-v1.json").write_bytes(
        (DATA / "curvature-sweep-v1.json").read_bytes()
    )
    print(f"Generated three provenance-bearing examples in {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
