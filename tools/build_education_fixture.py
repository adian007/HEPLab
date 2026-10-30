"""Create a deterministic synthetic first-experiment config and result artifact."""

# The generated self-contained HTML page is kept in one f-string template.
# ruff: noqa: E501

from __future__ import annotations

import html
import json
import threading
from pathlib import Path

from heplab import __version__
from heplab.io.provenance import config_hash
from heplab.physics.constants import CURVATURE_GEV_T_METRES
from heplab.server.workbench import RunConfig, analyze_events, bench

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web/HEPLab.Web/wwwroot/examples"
CONFIG = RunConfig(
    mode="analytic",
    backend="reference",
    seed=731,
    events=1,
    momentum_gev=5.0,
    bz_tesla=3.8,
    thickness_mm=1.0,
    noise_adc=0.0,
    threshold_adc=0.0,
    response_model="ideal",
    field_model="ideal_bore",
    source_model="transverse_pair",
)


def main() -> None:
    config = CONFIG.model_dump()
    result = bench(CONFIG, threading.Event(), event=0)
    analysis = analyze_events([result])
    result.update(events=1, analysis=analysis, config=config)
    result["fixture_scope"] = (
        "synthetic declared back-to-back muon pair; no collision generation, CMS event, "
        "or detector calibration"
    )
    result["run_config_v2"] = CONFIG.to_envelope()
    digest_payload = {
        key: value for key, value in result.items() if key not in {"artifact", "output_directory"}
    }
    artifact = {
        "format": "heplab-workbench-result-v2",
        "schema": "heplab-run-artifact-v1",
        "scope": "full_run",
        "run_id": "static-synthetic-first-experiment-v1",
        "parent_run_sha256": None,
        "result_sha256": config_hash(digest_payload),
        "model_ids": [component["id"] for component in result["model_spec"]["components"]],
        "heplab_version": __version__,
        "created_utc": None,
        "config_sha256": config_hash(config),
        "static_fixture": True,
    }
    result["artifact"] = artifact
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "analytic-muon-pair-config-v2.json").write_text(
        json.dumps(CONFIG.to_envelope(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result_text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    result_path = OUTPUT / "analytic-muon-pair-result-v1.json"
    result_path.write_text(
        result_text,
        encoding="utf-8",
        newline="\n",
    )
    track = result["tracks"][0]
    momentum = track["truth"]["momentum"]
    pt = (momentum["px"] ** 2 + momentum["py"] ** 2) ** 0.5
    radius = pt / (CURVATURE_GEV_T_METRES * abs(track["charge"] * CONFIG.bz_tesla))
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(crossing['surface_id'])}</td>"
        f"<td>{crossing['path_m']:.6f}</td>"
        + "".join(f"<td>{value:.6f}</td>" for value in crossing["position_m"])
        + "</tr>"
        for crossing in track["trajectory"]["crossings"]
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Declared muon pair · HEPLab</title><style>body{{font:16px/1.55 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}}.notice{{border:2px solid #a76200;padding:1rem;border-radius:.6rem}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:.45rem;border-bottom:1px solid #8886}}code{{overflow-wrap:anywhere}}a{{color:#16707b}}</style></head><body><p><a href="/gallery/">← HEPLab examples</a></p><p><strong>Synthetic fixture · educational analytic workbench</strong></p><h1>Follow a declared muon pair</h1><section class="notice">These are model paths and predicted guide-surface crossings for a declared back-to-back test pair. They are not CMS events, detector hits, or measured trajectories. The run uses a continuous PDG-table mean loss, a Gaussian Highland scattering core, and separate illustrative electronics.</section><h2>Expected field result</h2><p>For each 5 GeV/c transverse muon in a uniform 3.8 T ideal field, the analytic radius is pT/(0.299792458 |q| B) = {radius:.6f} m. The run applies the field over its declared 1 m segment, then uses one illustrative 1 mm silicon slab.</p><h2>Predicted crossings for μ−</h2><table><thead><tr><th>Guide surface</th><th>Path (m)</th><th>x (m)</th><th>y (m)</th><th>z (m)</th></tr></thead><tbody>{rows}</tbody></table><h2>Material ledger</h2><p>Mean deposit: {track["material"]["deposit_gev"] * 1000:.6f} MeV. Energy residual: {track["material"]["energy_residual_gev"]:.3e} GeV. The residual checks continuous bookkeeping only; the medium recoil is not tracked.</p><h2>Provenance</h2><ul><li>Run artifact digest: <code>{result["artifact"]["result_sha256"]}</code></li><li>Model IDs: <code>{html.escape(", ".join(result["artifact"]["model_ids"]))}</code></li><li>Seed: {CONFIG.seed}; software version: {html.escape(__version__)}</li><li><a href="analytic-muon-pair-config-v2.json">Download grouped setup</a></li><li><a href="analytic-muon-pair-result-v1.json">Download full synthetic result artifact</a></li></ul><p><a href="/validation/evidence/">Read evidence definitions</a></p></body></html>\n"""
    (OUTPUT / "analytic-muon-pair-event.html").write_text(page, encoding="utf-8", newline="\n")
    print(f"Generated synthetic fixture result sha256={artifact['result_sha256']}")


if __name__ == "__main__":
    main()
