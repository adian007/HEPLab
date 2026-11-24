"""Replay an exported Z-boson result in a fresh kernel with external sockets blocked."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

OFFLINE_CELL = """
import socket
import sys

def loopback_only(event, args):
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event == "socket.connect" and isinstance(args[1], tuple):
        host = args[1][0]
    else:
        return
    if host not in {"127.0.0.1", "::1", "localhost", None}:
        raise PermissionError("External network disabled during HEPLab notebook acceptance")

sys.addaudithook(loopback_only)
try:
    socket.getaddrinfo("192.0.2.1", 443)
except PermissionError:
    pass
else:
    raise AssertionError("offline guard did not reject the test address")
"""


def main() -> None:
    import nbformat
    from jupyter_client import KernelManager
    from nbclient import NotebookClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    notebook = nbformat.read(args.notebook, as_version=4)
    nbformat.validate(notebook)
    notebook.cells.insert(0, nbformat.v4.new_code_cell(OFFLINE_CELL))
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec.argv[0] = sys.executable
    with tempfile.TemporaryDirectory(prefix="heplab-z-notebook-") as scratch:
        shutil.copyfile(args.result, Path(scratch) / "heplab-z-boson-result.json")
        client = NotebookClient(notebook, km=manager, timeout=120)
        client.execute(cwd=scratch, cleanup_kc=True)
    by_id = {cell.id: cell for cell in notebook.cells}

    def output(identity):
        return "".join(x.text for x in by_id[identity].outputs if x.output_type == "stream")

    replay = output("workbench-load")
    comparison = output("workbench-compare")
    if "Reproduced the Workbench cutflow and mass histogram." not in replay:
        raise ValueError("Notebook did not replay the supplied Workbench artifact")
    if "Selected pairs:" not in comparison:
        raise ValueError("Notebook did not complete the one-cut comparison")
    print(replay + comparison)


if __name__ == "__main__":
    main()
