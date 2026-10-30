"""Verify catalog, alias and certification resources from an isolated wheel import."""

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel")
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    with tempfile.TemporaryDirectory(prefix="heplab-wheel-") as folder:
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(folder)
        script = """import json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from heplab import catalog
from importlib.resources import files
status=json.loads(files("heplab").joinpath("data/project-capabilities.json").read_text())
assert {x["id"] for x in status}=={"data","simulation","analysis","evidence"}
from heplab.io.certification import LumiMask
from heplab.io.provenance import source_snapshot,file_hash
value,path=catalog.get("Run2016G_DoubleMuon")
alias,_=catalog.get("Run2016_DoubleMuon")
assert value==alias and value["record"]==30522
assert len(list(catalog.list_datasets()))==1
cert=path.parent.parent/value["certification"]["path"]
assert file_hash(cert)==value["certification"]["sha256"]
assert LumiMask(cert).sha256
from heplab.server.data_workspace import certification_path
assert LumiMask(certification_path(pathlib.Path(str(files("heplab")))/"data/cms-samples")).sha256 == LumiMask(cert).sha256
assert source_snapshot()!=__import__("hashlib").sha256(b"{}").hexdigest()
import heplab.server
ui=pathlib.Path(heplab.server.__file__).parent/"static"
assert all((ui/name).is_file() for name in ("index.html","workbench.css","workbench.js"))
from heplab.physics.detector import geometry,silicon_stopping_power
from heplab.physics.calibration import muon_response_parameters
assert len(geometry()["surfaces"])==9
assert silicon_stopping_power(1.0)[0]>0
assert muon_response_parameters(45.,0.)["momentum_scale"]>0
from heplab.physics.cms_sources import display_manifest,display_asset
assert len(display_manifest()["layers"])==7
assert all(display_asset(x["id"]).is_file() for x in display_manifest()["layers"])
assert all(display_asset(x["id"]+suffix).is_file() for x in display_manifest()["layers"] for suffix in ["-surfaces","-surface-outlines"])
from heplab.physics.cms_field import tracker_field
assert 3.7<tracker_field([0.,0.,0.])[2]<3.9
from heplab.physics.calibration import REFERENCE
assert all((REFERENCE/(name+".json")).is_file() for name in
           ["cms-field-validation","cms-field-points","cms-measured-validation",
            "cms-mass-calibration","cms-resonance-validation",
            "cms-resonance-data-report","cms-resonance-selected-pairs",
           "cms-resonance-data-report-v2","cms-resonance-selected-pairs-v2",
           "cms-resonance-data-report-target-dependent-legacy",
            "cms-z-template-candidates"])
print("PASS: isolated wheel catalog, alias, certification and package source snapshot")
"""
        subprocess.run([sys.executable, "-I", "-c", script, folder], check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
