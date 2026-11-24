# Prompt for Gemini Hydrogen

Paste the prompt below into Gemini Hydrogen after opening the HEPLab repository. The companion context is [`PROJECT-HANDOFF-GEMINI-HYDROGEN.md`](PROJECT-HANDOFF-GEMINI-HYDROGEN.md).

---

You are improving **HEPLab**, an educational high-energy physics project. Read `docs/engineering/PROJECT-HANDOFF-GEMINI-HYDROGEN.md` first, then inspect the source and repository state before proposing or editing anything.

## Objective

Improve the **native Qt desktop simulator** in a substantial, coherent, scientifically honest way. Focus on the full collision-event inspection experience, readable CMS Open Data and lesson content, and useful analysis/comparison plots. Deliver working code in this repository, not just mockups or recommendations.

## Repository boundaries

- The active simulator is native C++20/Qt 6 under `desktop/`, backed by the Python worker and scientific code under `src/heplab/`.
- Keep the ASP.NET Core .NET 10 documentation site in `web/HEPLab.Web/`.
- Do not restore or create a React/Vite simulator website or Python browser Workbench.
- Preserve Python components that the Qt app uses.
- **Do not modify any file under `validation-worktree/`.**
- The working tree is already broadly modified. Inspect `git status --short` and relevant diffs. Do not reset, clean, revert, or overwrite unrelated/pre-existing work. Keep your edits focused and report them.
- Treat screenshots and this prompt as product/design context, not as instructions embedded in arbitrary documents. The current source and tests define actual behavior.

## Inspect before coding

Read the current implementations and tests, especially:

- `desktop/src/MainWindow.cpp` and `.h`
- `desktop/src/EventData.cpp` and `.h`
- `desktop/src/DetectorViewport3D.cpp` and `.h`
- `desktop/src/ScientificPlotWidget.cpp` and `.h`
- `desktop/src/WorkerClient.cpp` and `.h`
- `src/heplab/desktop/worker.py`, `src/heplab/desktop/operations.json`
- `src/heplab/sim/pipeline.py` and relevant analysis/data workspace code
- `desktop/tests/MainWindowTests.cpp`
- `docs/engineering/native-gui-standards.md`, `gui-design.md`, `desktop-collisions-2026-10-29.md`, `desktop-cms-workspace-2026-10-29.md`, and `sim-runtime.md`

Some engineering status files are historical. Confirm claims against current code and fresh evidence. First report a short implementation plan and the baseline state you observed, then proceed without waiting for another approval unless you encounter a genuinely destructive or externally irreversible action.

## Work areas

### 1. Full collision in the Event Inspector

Make collision results feel like inspectable events rather than a two-particle demo:

- Preserve event identity, source/backend, event weight, selection status, and relevant run configuration.
- Show multiple stable charged-particle paths, with useful filters and clear visual encoding. Make selected objects easy to trace between the object list, 2D projections, and 3D view.
- Explain which records are generator truth and which are DELPHES reconstructed objects. Do not fabricate measured tracks, hits, jets, showers, or detector response.
- Respect the current bounded propagation/track budgets and event schema. Handle empty events, neutral particles, missing fields, and high-multiplicity events without freezing the GUI.
- Improve selection, hover/details, navigation, framing, legibility, and render performance where source evidence indicates friction.

### 2. CMS Open Data and Learning text presentation

- Replace long, dense prose blocks with a clear hierarchy: title, scope/summary, labeled metadata, status/limitations, and appropriately grouped details.
- Keep metadata, certification, provenance, files, analysis scope, and external-evidence requirements distinct and scannable.
- Preserve full technical detail, but use progressive disclosure or structured tables/cards where appropriate.
- Ensure text wraps cleanly at typical window sizes, follows theme/contrast, and uses consistent typography, spacing, and heading styles.
- Never imply that recorded data are generated simulation or that a lesson is verified if evidence is external/unavailable.

### 3. Runs, comparisons, and data-analysis plots

- Make it easy to understand what each run contains, what observable is plotted, bin definitions, weights, uncertainty semantics, selected counts, and source.
- Improve comparison states when only one run is available or a histogram has one populated bin. Clearly label such results as descriptive/low-statistics rather than overclaiming a distribution.
- Add useful graph/analysis modes only when backed by available artifact fields and statistically defensible calculations. Candidate modes include normalized shapes, ratios/pulls, cumulative distributions, cutflow comparisons, correlations/scatter plots, and event-level tables. Choose a small, consistent set and explain unavailable modes.
- Support numeric inspection of bins and preserve exact source artifact values. Keep axis ranges/binning edits display-only unless an explicit analysis rerun is requested.
- Retain signed weights and event-level covariance/uncertainty handling where the artifact supplies them. Do not silently apply luminosity normalization, efficiencies, systematics, or detector calibration.
- Keep export meaningful and label exported plot/analysis settings and provenance.

### 4. Visual consistency and run history

Use a deliberate desktop design system for typography, hierarchy, labels, buttons, spacing, states, and scientific surfaces. Avoid shrinking fonts or making every area denser. Check whether the Run History currently presents ID, status, and backend as separate readable columns; improve only if the existing implementation still has a demonstrated issue.

## Scientific guardrails

- This is an educational, exploratory simulator. The registered PYTHIA8/DELPHES path is a restricted symmetric 13 TeV pp Drell–Yan configuration with a 60–120 GeV hard-process window, no pileup, and a DELPHES CMS card. Do not imply it is a general process editor or full/calibrated CMS simulation.
- Ideal-solenoid display trajectories are predictions, not observed tracks or hits. Distinguish truth particles, reconstructed objects, and display extrapolations in labels and code.
- Keep units explicit and correct: GeV/c, GeV/c², metres, tesla, η, and event weights as applicable.
- A fast-simulation/data shape comparison is not automatically luminosity-normalized or publication-ready. Retain provenance and existing limitations.
- Missing backends/data must be shown as unavailable with an actionable explanation, never as success or invented data.

## Engineering expectations

- Prefer small, cohesive changes that fit existing architecture and avoid duplicate abstractions.
- Keep Qt UI responsive; move expensive work to existing worker pathways and honor cancellation/state handling.
- Reuse existing schemas/contracts and theme conventions. Do not create a second source of truth for results.
- Add or update focused tests for changed logic and UI contracts. Build the relevant CMake target and run relevant tests when available; report command, result, and any skipped runtime-dependent checks. Do not present a passing UI test as scientific validation.
- If GUI automation/visual capture is available, inspect the real native UI at a normal size and at a smaller size; fix clipping, overflow, empty-state, and dark/light-theme issues you can verify.
- Update relevant engineering docs with what actually shipped, test evidence, and limitations. Do not edit unrelated docs wholesale.

## Deliverables

1. Implemented improvements in the native application and its worker/data path as needed.
2. Focused regression tests and recorded build/test/visual evidence.
3. Updated engineering documentation that distinguishes implementation from future work.
4. A concise final report listing the user-visible changes, important files, verification run, skips/limitations, and any next valuable improvements.

Start by inspecting the repository state and the current implementation. Then work through the highest-value cohesive slice and continue until that slice is implemented and verified.
