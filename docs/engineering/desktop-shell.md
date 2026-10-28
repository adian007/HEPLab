# Desktop simulator app (M7 foundation)

Status, 2026-10-28: **the HEPLab simulator workbench runs as a native Windows
x86-64 desktop app.** Researchers can set up a run, simulate, inspect particles
in the 3D CMS view and export results, with no Python install, no browser and
no local web server. The IPC core and frozen worker are also tested on Linux
x86-64. Linux and macOS bundles have not been built yet; their first build is
the [desktop workflow](../../.github/workflows/desktop.yml). Nothing is signed
or distributed, and the Windows installer has not been run.

```mermaid
flowchart LR
  UI[Simulator workbench in WebView2] -->|invoke heplab_invoke| Shell[Tauri shell]
  UI -->|same-origin, SHA-256 checked| Layers[(Bundled CMS display layers)]
  Shell --> Validate[Operation table check]
  Validate --> Sup[Supervisor: no shell, fixed argv]
  Sup -->|JSON lines over stdio| Worker[Frozen heplab-worker sidecar]
  Worker --> Confine[Second check and project-root confinement]
  Confine --> Jobs[Workbench job engine]
  Confine --> Lib[heplab Python and Rust physics]
  Table[(operations.json)] --> Validate
  Table --> Confine
```

## What a user gets

The app window is the same workbench as `heplab gui`
(`src/heplab/server/static`), copied unchanged by `desktop/prepare_frontend.py`
at build time. Its model browser, XY/XZ/3D viewport with CMS iSpy outlines,
parameters, Run/Stop, run history, particle, crossing, calibration and
capability tabs, and *Export result* all work. Run artifacts are written to the
app's data directory (`%APPDATA%\org.heplab.desktop\projects\default\artifacts`
on Windows).

The **analytic muon thin-slab bench** (Python reference engine) runs inside the
app. The **Drell–Yan PYTHIA8/DELPHES** mode needs the native Linux simulation
runtime, so the desktop app reports it unavailable and keeps it disabled; that
is the optional CMS/native capability tracked by DESKTOP-006.

## Components

| Part | Location | Behaviour |
|---|---|---|
| Operation table | `src/heplab/desktop/operations.json` | The only operations that exist: workbench session, detector geometry and display manifest, calibration report, job submit/get/cancel/event, project overview and evidence, engine capabilities, datasets, runs list/get, lab profile and replay. Argument types are `id`, `path`, `number`, `integer` and `object` (structure only; job configs are validated by the workbench's strict `RunConfig` model). Rust reads the table with `include_str!` and the worker loads the same file. |
| Worker | `heplab.desktop.worker` | Announces protocol, version and operation list, then answers one JSON line per request. Re-validates every request. Holds one workbench `Jobs` engine, the same class the web server uses, and cancels running simulations when the shell closes its input. Paths must be plain relative paths, never follow symlinks, and stay inside the project root. |
| IPC core | `desktop/core` (std + serde, plus `windows-sys` or `libc`) | Validates before launching anything. Spawns an explicit executable with a fixed argument vector and no console window. Checks protocol, exact version and the operation set during the handshake. Size-limited reads, per-operation timeouts, and cancellation that kills the whole worker process tree (a kill-on-close Job Object on Windows, a process group on Unix) and restarts it on the next call. |
| Workbench transport | `src/heplab/server/static/workbench.js` | When `window.__TAURI_INTERNALS__` exists, the existing `api()` helper maps its 9 paths to operations, and display layers load from the bundled `cms-display/` files with the existing SHA-256 checks. In a browser nothing changes. |
| Shell | `desktop/src-tauri` | Two commands (`heplab_invoke`, `heplab_cancel`). No shell/fs/http plugins. CSP: scripts, styles, fonts and connections from `self` and Tauri IPC only. On exit it cancels in-flight work and waits at most 3 s for the worker lock before shutting the worker down. |
| Packaging | `desktop/build_worker.py`, `desktop/prepare_frontend.py` | PyInstaller one-file sidecar named for the Rust host triple, checked by a handshake with every `PYTHON*` environment variable removed. The frontend step copies the workbench and verifies each display layer against its manifest hash. |
| Matrix | `.github/workflows/desktop.yml` | Windows x86-64 (NSIS/MSI), Linux x86-64 (AppImage/deb/rpm, Ubuntu 22.04 baseline), macOS Intel and Apple silicon (app/DMG, minimum macOS 11). Each runner confirms its native host triple, then freezes, tests and bundles. Bundle hashes are recorded and bundles are uploaded unsigned. |

## Evidence so far

- 21 worker tests, including a full simulator job through the worker
  (submit, idempotent resubmit, poll to completion, event fetch, artifact
  written), rejection of extra config fields and non-integer event indices,
  web/desktop payload equality, and path, size and shell-argument rejections.
- 14 Rust tests (5 unit, 9 integration), passing natively on Windows and
  Linux, including cancellation that kills a grandchild process. `cargo
  clippy -D warnings` and `rustfmt` are clean for the core and the shell.
- Windows x86-64 (Rust 1.99.1, MSVC 14.51, Windows SDK 10.0.26100, WebView2
  156): release build with an 11.2 MB frozen worker and an unsigned NSIS
  installer.
- Driving the running app as a user: the workbench loaded, connected to the
  worker and loaded all 7 CMS display layers with SHA-256 verified. Pressing
  Run on the analytic bench completed (*validation: educational_unvalidated*),
  filled the particle table with the two 45 GeV muons (0.5508 MeV deposit,
  55/54 ADC), and *Export result* saved a 179 KB JSON file. The app then
  closed with no worker processes left. Force-killing the app also left none.
- Security checks from inside the live webview: unknown operations and path
  escapes are refused by the shell, external `fetch` is blocked by the CSP,
  and `plugin:shell|execute` is refused by Tauri's permission check.
- Defects found and fixed on the way: orphaned Python children after
  cancellation, the workbench Run button staying disabled (it requires a
  session token), CMS display layers blocked by a missing `connect-src
  'self'`, and a possible exit hang on a held worker lock.

## Not done

- PYTHIA8/DELPHES collision mode inside the app (DESKTOP-006); Linux and
  macOS bundles (DESKTOP-001); cross-architecture numerical fixtures
  (DESKTOP-004); signing, notarization, updater and uninstall checks
  (DESKTOP-005).
- The Rust engine option is offered only if the frozen worker can find a
  Rust backend; release bundles do not ship one yet, so the Python reference
  engine is used.
- On Windows the worker joins its Job Object just after spawn. A child started
  in that gap of microseconds would not be contained. The PyInstaller
  bootloader unpacks its files before starting Python, so this gap is not hit
  in practice; closing it fully needs a suspended start.
- `web/src/lib/desktop.ts` (the project website's desktop transport) remains,
  but the app now ships the simulator workbench, not the website.
