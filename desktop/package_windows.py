"""Stage a portable Windows x64 Workbench with its frozen worker."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def msvc_runtime() -> Path:
    vswhere = (
        Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    install = subprocess.check_output(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        text=True,
    ).strip()
    candidates = sorted(
        (Path(install) / "VC/Redist/MSVC").glob("*/x64/Microsoft.VC143.CRT"),
        key=lambda path: tuple(map(int, path.parents[1].name.split("."))),
    )
    if not candidates:
        raise SystemExit("Install the Visual Studio 2022 x64 C++ redistributable build files.")
    return candidates[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path, help="Release HEPLabWorkbench.exe")
    parser.add_argument("--qt-bin", required=True, type=Path, help="Qt 6 MSVC x64 bin directory")
    parser.add_argument("--output", required=True, type=Path, help="New bundle directory")
    args = parser.parse_args()
    if sys.platform != "win32" or platform.machine() != "AMD64" or sys.maxsize < 2**32:
        parser.error("Build with 64-bit Python on Windows x64.")
    app = args.exe.resolve(strict=True)
    qt_bin = args.qt_bin.resolve(strict=True)
    output = args.output.absolute()
    if output.exists():
        parser.error(f"Bundle directory already exists: {output}")
    crt = msvc_runtime()

    # Freezing the installed wheel includes the package data assembled by Hatch,
    # including dataset manifests and luminosity certification.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="heplab-package-", dir=output.parent) as temporary:
        work = Path(temporary)
        stage = work / "bundle"
        stage.mkdir()
        shutil.copy2(app, stage / "HEPLabWorkbench.exe")
        subprocess.run(
            [
                str(qt_bin / "windeployqt.exe"),
                "--release",
                "--no-compiler-runtime",
                str(stage / "HEPLabWorkbench.exe"),
            ],
            check=True,
        )
        for dll in crt.glob("*.dll"):
            shutil.copy2(dll, stage)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--onedir",
                "--noupx",
                "--name",
                "heplab-worker",
                "--collect-data",
                "heplab",
                "--hidden-import",
                "heplab_kernels",
                "--collect-all",
                "awkward_cpp",
                "--add-data",
                f"{ROOT / 'src/heplab/sim/worker.py'}:heplab/sim",
                "--distpath",
                str(work),
                "--workpath",
                str(work / "freeze"),
                "--specpath",
                str(work),
                str(ROOT / "desktop/worker_entry.py"),
            ],
            check=True,
        )
        worker = stage / "worker"
        (work / "heplab-worker").rename(worker)
        for dll in crt.glob("*.dll"):
            shutil.copy2(dll, worker)
        shutil.copy2(ROOT / "LICENSE", stage)
        shutil.copytree(ROOT / "notebooks/gallery", stage / "notebooks/gallery")
        stage.rename(output)
    print(output)


if __name__ == "__main__":
    main()
