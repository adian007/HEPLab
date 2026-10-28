"""Run inside the activated Linux conda runtime after installing environment.yml.

Freeze the complete resolved package URLs, native executable and detector cards.
The environment specification is a solver input, not a reproducible lock itself.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

prefix = Path(os.environ["CONDA_PREFIX"])
records = [json.loads(p.read_text()) for p in (prefix / "conda-meta").glob("*.json")]
versions = {r["name"]: r["version"] for r in records}
expected = {"pythia8": "8.312", "delphes": "3.5.1", "root_base": "6.40.04"}
assert all(versions.get(k) == v for k, v in expected.items()), "incompatible runtime"
binary = prefix / "bin/DelphesPythia8"
assert binary.is_file(), "package does not contain integrated driver"
cards = list(prefix.rglob("delphes_card_CMS.tcl"))
assert len(cards) == 1, "ambiguous CMS card"
# Normalize the package-dependent card layout without modifying upstream cards.
destination = prefix / "share/delphes/cards"
if cards[0].parent != destination and not destination.exists():
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(cards[0].parent, target_is_directory=True)
lines = ["@EXPLICIT"]
for record in sorted(records, key=lambda r: r["name"]):
    assert record.get("url") and record.get("sha256"), "package lacks URL or SHA256"
    lines.append(record["url"] + "#" + record["sha256"])
lock = "\n".join(lines) + "\n"
(prefix / "heplab-explicit.lock").write_text(lock)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


inventory = {
    "versions": expected,
    "explicit_lock_sha256": hashlib.sha256(lock.encode()).hexdigest(),
    "driver_sha256": digest(binary),
    "cards_sha256": {
        str(p.relative_to(cards[0].parent)): digest(p)
        for p in cards[0].parent.rglob("*")
        if p.is_file()
    },
    "package_count": len(records),
    "platform": "linux-64",
    "microarchitecture_level": versions.get("_x86_64-microarch-level"),
    "physics_inputs_sha256": {
        str(p.relative_to(prefix)): digest(p)
        for p in [
            *(prefix / "share/Pythia8").rglob("*"),
            prefix / "lib/libpythia8.so",
            prefix / "lib/libDelphes.so",
        ]
        if p.is_file()
    },
}
subprocess.run([str(prefix / "bin/root-config"), "--version"], check=True)
(prefix / "heplab-runtime.json").write_text(json.dumps(inventory, indent=2))
print(json.dumps(inventory, indent=2))
