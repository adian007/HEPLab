"""Run frozen held-out gates against actual PDG tables and native DELPHES samples."""

import argparse
import json
from pathlib import Path

from heplab.physics.calibration import REFERENCE, calibrate_delphes, calibrate_silicon

parser = argparse.ArgumentParser()
parser.add_argument("--training")
parser.add_argument("--heldout")
parser.add_argument("--output", default="artifacts/reference-calibration.json")
args = parser.parse_args()
report = {"silicon": calibrate_silicon()}
if args.training and args.heldout:
    report["muon_response"] = calibrate_delphes(args.training, args.heldout)
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
for name, value in report.items():
    print(name, value["status"])
    if value["status"] != "reference_calibrated":
        raise SystemExit("reference gate failed; report retained")
(REFERENCE / "silicon-calibration.json").write_text(json.dumps(report["silicon"], indent=2) + "\n")
if "muon_response" in report:
    (REFERENCE / "muon-response-calibration.json").write_text(
        json.dumps(report["muon_response"], indent=2) + "\n"
    )
