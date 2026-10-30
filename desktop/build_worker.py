"""Freeze the Python worker into a bundled folder and smoke-test the handshake.

Run on each native release runner: python desktop/build_worker.py
Requires PyInstaller in the build environment only; the result needs no system Python.
Output: desktop/src-tauri/worker/heplab-worker[.exe] plus its libraries, shipped as
a Tauri bundle resource.

The worker is frozen one-dir, not one-file. A one-file executable unpacks
Python and every library into a fresh temporary folder at each launch and only
removes it on a clean exit, so each forced stop (crash, wedge restart, app
kill) leaked that folder, and every start paid the unpack cost.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
ROOT = DESKTOP.parent


def host_triple() -> str:
    output = subprocess.check_output(["rustc", "-vV"], text=True)
    return next(line.split(": ", 1)[1] for line in output.splitlines() if line.startswith("host:"))


def smoke(binary: Path) -> dict:
    """Handshake plus one call, from an empty project, with no PYTHONPATH."""
    with tempfile.TemporaryDirectory() as project:
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        result = subprocess.run(
            [str(binary), "--project-root", project],
            input="\n".join(
                json.dumps({"id": identity, "op": op, "args": {}})
                for identity, op in [(1, "runs.list"), (2, "engine.capabilities")]
            )
            + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
            check=False,
        )
    if result.returncode:
        raise SystemExit(f"packaged worker failed to start:\n{result.stderr[-8000:]}")
    hello, reply, engine = (json.loads(line) for line in result.stdout.splitlines())
    if hello["protocol"] != "heplab-desktop-ipc-v1" or reply != {"id": 1, "ok": True, "result": []}:
        raise SystemExit(f"worker smoke test failed: {hello} {reply}")
    if not engine.get("ok") or not engine["result"]["rust_extension"]:
        raise SystemExit(f"packaged Rust engine is unavailable: {engine}")
    return hello


def main() -> int:
    if importlib.util.find_spec("heplab_kernels") is None:
        raise SystemExit(
            "Build and install the native kernels wheel before freezing the worker: "
            "maturin build --release --manifest-path kernels/Cargo.toml, then pip install the wheel"
        )
    for name in ("numpy", "awkward", "uproot"):
        if importlib.util.find_spec(name) is None:
            raise SystemExit(
                f"Collision-enabled desktop packaging requires {name}; install numpy awkward uproot"
            )
    # The backend is imported dynamically. PyInstaller cannot infer this import.
    from heplab.physics.engine import execute

    execute(
        {
            "op": "mass",
            "first": [45, 0, 0, 0.10565839],
            "second": [45, 0, 3.141592653589793, 0.10565839],
        },
        backend="rust",
    )
    triple = host_triple()
    suffix = ".exe" if sys.platform == "win32" else ""
    sample_args = []
    samples = ROOT / "artifacts/cms/measured"
    if all(
        (samples / name).is_file()
        for name in ("run2016g-100k.root", "source.json", "dy-ul16-100k.root", "dy-source.json")
    ):
        from heplab.io.provenance import file_hash

        bundled = [
            ("run2016g-100k.root", "source.json"),
            ("dy-ul16-100k.root", "dy-source.json"),
        ]
        # Optional display sidecars (tools/build_cms_display_projection.py).
        for name in ("run2016g-100k-display.root", "dy-ul16-100k-display.root"):
            if (samples / name).is_file():
                bundled.append((name, name.replace(".root", ".json")))
        for name, metadata in bundled:
            record = json.loads((samples / metadata).read_text(encoding="utf-8"))
            if file_hash(samples / name) != record["derived_file_sha256"]:
                raise SystemExit(f"Refusing to bundle changed CMS sample: {name}")
            for filename in (name, metadata):
                sample_args += [
                    "--add-data",
                    str(samples / filename) + os.pathsep + "heplab/data/cms-samples",
                ]
    # Imported data need certification even when optional sample ROOT files
    # are absent on the release runner.
    certification = (
        ROOT
        / "manifests/certification/Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.json"
    )
    sample_args += ["--add-data", str(certification) + os.pathsep + "heplab/data/cms-samples"]
    with tempfile.TemporaryDirectory() as work:
        entry = Path(work) / "heplab_worker_entry.py"
        entry.write_text(
            "import sys,os,faulthandler\n"
            "faulthandler.enable()\n"
            "if os.environ.get('HEPLAB_WORKER_TRACE') == '1':\n"
            "    faulthandler.dump_traceback_later(30, repeat=True)\n"
            # Windows DLL initialization can hang when NumPy first loads on a
            # background job thread in a frozen process. Load readers on the
            # main thread before the IPC loop can accept simulation jobs. The
            # packaged handshake smoke test also checks these imports succeed.
            "import numpy,awkward,uproot\n"
            "from heplab.desktop.worker import main\nsys.exit(main())\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--onedir",
                "--noconfirm",
                "--clean",
                "--name",
                "heplab-worker",
                "--collect-data",
                "heplab",
                "--hidden-import",
                "heplab_kernels",
                "--collect-all",
                "awkward_cpp",
                "--add-data",
                str(ROOT / "src/heplab/sim/worker.py") + os.pathsep + "heplab/sim",
                *sample_args,
                "--distpath",
                str(Path(work) / "dist"),
                "--workpath",
                str(Path(work) / "build"),
                "--specpath",
                work,
                str(entry),
            ],
            check=True,
        )
        built = Path(work) / "dist" / "heplab-worker"
        folder = DESKTOP / "src-tauri" / "worker"
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(built, folder, symlinks=True)
    target = folder / f"heplab-worker{suffix}"
    hello = smoke(target)
    print(json.dumps({"worker": str(target.relative_to(ROOT)), "triple": triple, **hello}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
