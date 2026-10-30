# Desktop collision workflow — 29 October 2026

The Windows desktop workbench now runs the installed PYTHIA8 8.312 / DELPHES
3.5.1 runtime through WSL Ubuntu. It discovers the installation without a special
launcher. Windows Python and Rust toolchains are not needed to use the bundle;
WSL and the separately provisioned pinned simulation runtime are required.

## Use it

Open `desktop/src-tauri/target/x86_64-pc-windows-msvc/release/heplab-desktop.exe`
with its adjacent `heplab-worker.exe`. Choose **Drell–Yan collisions** to generate
100 pp events. The properties panel sets event count (up to 1000), seed and
reconstructed-muon cuts. **Run** applies those parameters; **Run next seed**
generates an independent sample.

**Run analysis** displays weighted muon pT, pseudorapidity, dimuon mass and missing
pT, statistical error bars and a selection cutflow. The mass candidate is the
highest-scalar-pT isolated opposite-charge pair, ranked before the mass cut.
Muon histogram variances include correlations within each event. Comparisons use
raw generator weights on matching bins; there is no luminosity normalization.

**Event display → Next selected** skips events failing the current run's selection.
The display extrapolates reconstructed muons in an ideal solenoid; it does not
render fitted hits, calorimeter showers or jets. Jet counts and missing pT remain
available in event details and the exported event table.

**Export event table** saves every generated event, its weight, muon and jet counts,
missing pT, candidate mass and selection status as CSV. On this Windows setup the
native app saves it in Downloads. **Export result** saves analysis JSON. Full ROOT
data, cards, hashes and generator logs are retained under the run directory shown
below the cutflow. Completed runs reopen from Saved runs after restart.

## Fixes and evidence

- The frozen worker includes numpy, uproot, awkward and Awkward's native libraries.
  Readers initialize on its main thread to avoid a frozen NumPy import hang.
- Simulation child processes cannot inherit the worker's input pipe. This fixes
  WSL consuming desktop requests while a background job runs.
- Runtime discovery recognizes Windows WSL distribution output and respects
  explicit installation settings. Read-only WSL metadata requests retry one
  timeout, then report a failure.
- Collision momentum is labeled reconstructed pT; generator conservation badges
  use the same ROOT-rounding tolerance as the backend.

Focused Python tests cover signed weights, event-level histogram uncertainty,
mass-unbiased candidate ranking, selection changes, missing measurements, WSL
discovery, input isolation, bounded timeout retry and worker operations.
The desktop IPC core also passes its lifecycle tests with the frozen worker.

Local evidence is in `output/desktop-collisions/`:

- `frozen-collision-acceptance.json`: 100 events, 33 selected, event navigation,
  restart reopening, and active 1000-event cancellation without partial publication.
- `Supervised Project/supervisor-acceptance.json`: the same generation/reopening
  path through the actual desktop process supervisor.
- `native-acceptance.json`: generation, event 3 navigation and 100-row CSV export
  driven in the native Windows interface.
- `browser-acceptance.json`: four plots, five cutflow stages, selected-event
  navigation, 100-row export and no browser console errors.

Run the optional real-runtime supervisor acceptance with:

```powershell
cargo run --locked --manifest-path desktop/core/Cargo.toml --example collision_acceptance -- WORKER_EXE NEW_PROJECT_DIRECTORY
```

The unsigned NSIS installer is built in the release directory's `bundle/nsis/`.
Installer and uninstaller lifecycle testing is still pending.

## Scientific boundary

This is a working exploratory collision workflow, restricted to symmetric 13 TeV
pp gamma*/Z → muons, a 60–120 GeV hard-process mass window, Monash tune / internal
PDF set 13 and the DELPHES CMS card, with no pileup. It is not a general process
editor or calibrated CMS simulation. The generator cross section and detector
response have not been independently validated for publication. The seed-42
100-event sample gives 113 reconstructed muons, 33 selected events, a generator
estimate of 1341 ± 78.97 pb and maximum truth four-momentum residual 0.000276 GeV.
Those values are acceptance evidence, not a physics validation claim.
