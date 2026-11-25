# Windows Workbench packaging and acceptance

The [desktop workflow](../../.github/workflows/desktop.yml) builds the x64
Release configuration with Qt 6.8.3 and Visual Studio 2022. It freezes the
installed HEPLab wheel and the Rust kernel extension into a worker directory.
The portable bundle includes Qt plugins, the MSVC runtime, and Python 3.12.
Extract the entire bundle to a local directory and keep its directory layout
intact. Projects and run artifacts are saved to the user's workspace.
The workflow runs the portable smoke test on a separate runner using only
the two uploaded artifacts.

The portable bundle supports offline analytic simulations. Collision runs
using PYTHIA8 and DELPHES require the separately provisioned
[simulation runtime](sim-runtime.md).

## Package from a developer checkout

Use x64 Python 3.12, Visual Studio 2022 with the C++ desktop workload, Qt
6.8.3 for MSVC x64, CMake, uv, and the repository's Rust toolchain. In
PowerShell, set `QT_ROOT_DIR` to the Qt installation for this architecture.

```powershell
uv sync --locked --no-editable --no-dev --extra serve --extra analysis
uvx --from "maturin==1.16.0" maturin build --release --locked --interpreter .venv/Scripts/python.exe --manifest-path kernels/Cargo.toml --out build/worker-wheels
uv pip install --no-deps --find-links build/worker-wheels heplab-kernels
uv pip install "pyinstaller==6.22.3" "pyinstaller-hooks-contrib==2026.9"
cmake -S . -B build/desktop-ci -G "Visual Studio 17 2022" -A x64 "-DQt6_DIR=$env:QT_ROOT_DIR/lib/cmake/Qt6"
cmake --build build/desktop-ci --config Release --parallel
.venv/Scripts/python.exe desktop/package_windows.py --exe build/desktop-ci/desktop/Release/HEPLabWorkbench.exe --qt-bin "$env:QT_ROOT_DIR/bin" --output build/HEPLabWorkbench-win-x64
$kit = New-Item -ItemType Directory build/HEPLabWorkbench-smoke
Copy-Item desktop/verify_windows_package.ps1,build/desktop-ci/desktop/Release/heplab_desktop_tests.exe,"$env:QT_ROOT_DIR/bin/Qt6Test.dll" -Destination $kit.FullName
```

## Verify on a clean Windows machine

Use a fresh x64 Windows desktop with Python, Qt, and the HEPLab checkout
absent. Copy only the extracted Workbench and smoke kit folders to the
machine. Use a Windows desktop session with graphics available. From the
parent directory of both folders, run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\HEPLabWorkbench-smoke\verify_windows_package.ps1 -Bundle .\HEPLabWorkbench-win-x64
```

The verifier copies the app to a new directory containing spaces and launches
it from an empty working directory with a Windows-only `PATH`. It checks
that the Workbench and its worker load the bundled Qt and Python DLLs. The
Qt smoke test then submits a simulation through the Workbench, inspects the
resulting tracks, and checks that a completed run publishes a JSON artifact.
Record the Windows version and the test output for release acceptance.
