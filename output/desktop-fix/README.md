# HEPLab desktop laboratory update

Built and verified on Windows x86-64, 28 October 2026.

The running desktop application now uses the bundled Rust engine. Its default
angular sample contains 32 distinct seeded muon-pair events, with aggregate plots
of transverse momentum, dimuon invariant mass, pseudorapidity, and channel signal
(switchable to ionization deposit). Truth and sampled tracking response are shown
separately. These are synthetic muon experiments, not collision data.

Use **Run analysis** for distributions and saved-run comparison, **Event display**
and Previous/Next for individual trajectories, and **Run next seed** for an
independent sample. **Load setup** restores saved parameter JSON; completed runs
can be reopened from **Saved runs** after restarting the worker. The original
single transverse-pair fixture remains available in the Muon source selector.

The launchable application is
`desktop/src-tauri/target/x86_64-pc-windows-msvc/release/heplab-desktop.exe`.
Keep the adjacent `heplab-worker.exe` with it. The updated NSIS installer is under
that release directory's `bundle/nsis/` folder. The installer was built but was
not installed during this task.

Verification:

- 65 focused Python tests passed, including angular source kinematics, source
  reproducibility, response observables, persistence across restarts, cancellation,
  and Rust/reference parity.
- 14 numerical Rust core tests passed.
- The frozen worker, with Python/Rust environment overrides removed, completed
  an eight-event Rust sample and reopened its event 3 after a process restart:
  [packaged-acceptance.json](packaged-acceptance.json).
- The actual rebuilt native window completed run `55e304e4b55d453a7c9001c1`
  with Rust, 32 events and 64 truth muons. Native Next event changed pT from
  22.88361 to 44.47444 GeV/c and exposed an inefficient response sample. See
  [native-acceptance.json](native-acceptance.json) and
  [native-analysis.png](native-analysis.png).
- Browser acceptance passed charts, event navigation, comparisons, setup round
  trip, persisted-run reopening, minimum-width stale warning, active cancellation,
  and an injected conservation failure:
  [browser-check.json](browser-check.json).
- Ruff checks, JavaScript syntax check, and `git diff --check` passed.

The Rust fix includes the dynamic PyO3 import in the frozen worker, validates the
binding numerically during startup/build, and builds the kernels wheel in CI.
It no longer relies on a separately configured WSL executable for desktop Rust.

PYTHIA8/DELPHES collision generation remains unavailable in this Windows bundle;
the interface now explains that beside the commands. The added distributions do
not establish calibrated CMS detector response.
