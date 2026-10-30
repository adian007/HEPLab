"""Contract tests for checked-in, fixture-derived static site examples."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_generated_reference_pages_match_versioned_evidence():
    subprocess.run(
        [sys.executable, "tools/build_site_examples.py"], cwd=ROOT, check=True, capture_output=True
    )
    examples = ROOT / "web/HEPLab.Web/wwwroot/examples"
    pdg = (examples / "pdg-silicon-mean-loss.html").read_text(encoding="utf-8")
    cms = (examples / "cms-resonance-reference-regression-v2.html").read_text(encoding="utf-8")
    report = json.loads(
        (ROOT / "src/heplab/data/reference/cms-resonance-data-report-v2.json").read_text(
            encoding="utf-8"
        )
    )

    assert "Held-out reference row" in pdg
    assert "not a stochastic single-particle loss distribution" in pdg
    assert report["status"] == "failed_reference_regression"
    assert "gate: FAILED" in cms
    assert "not an independent dataset" in cms
    assert "does not use a PDG target mass" in cms
    assert "0.049300" in cms
    curvature = (examples / "curvature-sagitta-sweep-v1.html").read_text(encoding="utf-8")
    sweep = json.loads((examples / "curvature-sweep-v1.json").read_text(encoding="utf-8"))
    assert len(sweep["result"]["ideal_uniform_field"]) == 32
    assert len(sweep["result"]["tracker_oae_reference"]) == 8
    assert "no field-measurement acceptance threshold" in curvature
    for source, expected in sweep["source_sha256"].items():
        actual = hashlib.sha256((ROOT / source).read_bytes()).hexdigest()
        assert actual == expected


def test_downloadable_first_experiment_is_a_real_synthetic_workbench_artifact():
    from heplab.io.provenance import config_hash
    from heplab.server.workbench import RunConfig

    subprocess.run(
        [sys.executable, "tools/build_education_fixture.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    examples = ROOT / "web/HEPLab.Web/wwwroot/examples"
    config = json.loads(
        (examples / "analytic-muon-pair-config-v2.json").read_text(encoding="utf-8")
    )
    result = json.loads(
        (examples / "analytic-muon-pair-result-v1.json").read_text(encoding="utf-8")
    )
    restored = RunConfig.model_validate(config)
    assert restored.seed == 731
    assert result["fixture_scope"].startswith("synthetic declared back-to-back muon pair")
    assert result["artifact"]["static_fixture"] is True
    assert result["artifact"]["scope"] == "full_run"
    assert result["artifact"]["result_sha256"] == config_hash(
        {key: value for key, value in result.items() if key not in {"artifact", "output_directory"}}
    )
    assert len(result["tracks"]) == 2
