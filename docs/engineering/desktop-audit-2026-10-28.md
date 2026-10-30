# Desktop application audit — 28 October 2026

## Verdict

**The reference simulation works, but I would not use this desktop build as a research analysis environment yet.** It is a useful educational muon transport bench with a detector display. The most urgent problems are trust in the check badges, recovery of saved work, and the connection between the displayed result and the editable parameters.

This is an audit of the current implementation, not a claim that all planned capabilities should already exist. An unavailable engine is different from a broken button. Missing desktop analysis workflows are identified separately below.

## What was actually tested

- **Native Windows application:** ran the existing release executable, connected to its packaged worker, submitted the default reference bench, inspected the completed particle table and inspector, and observed a fresh session after relaunch. The tested native job was `6a879967bea138e52fea846b`.
- **Packaged executable worker:** exercised the shipped `heplab-worker.exe` through its actual JSON-lines protocol in an isolated audit project. Eight runs completed: default, repeat, zero field, doubled slab thickness, saturated electronics, threshold suppression, CMS tracker field, and DY reference response. An incompatible response configuration was correctly rejected.
- **Shared interface in Edge:** tested the current source workbench at an isolated local server on port 8766. Exercised Run, the three projections, Region, Fit, grid and outline toggles, particle selection, crossings, reference validation, capability report, Undo/Redo, setup download, result export, run recall, mode changes, numeric validation, guided-tour start/finish, refresh recovery, and the minimum desktop window dimensions.
- **Automated source tests:** 58 passed, with one Starlette/httpx deprecation warning. Scope: `test_desktop_worker.py`, `test_material_and_workbench.py`, `test_physics_reference.py`, `test_cms_material_and_mass.py`, and `test_project_capabilities.py`.

The source and generated desktop copies of `workbench.js` and `index.html` had identical SHA-256 hashes. This supports attributing shared UI logic defects to the desktop implementation; it does **not** substitute for native WebView2 interaction tests.

### Limits of the native test

After the first successful native run, Windows UI control became unreliable. The controller reported a minimized window, unavailable coordinate geometry, and missing foreground process IDs. The user restored the window, but input errors continued. These are recorded as automation limitations, **not app crashes or broken buttons**. A disappearing earlier window has no established cause and is not counted as a crash.

Consequently, native Save/Export dialogs, the entire native guided tour, genuine mid-computation Stop behavior, long-session responsiveness, and installer lifecycle are **not certified by this audit**. Browser downloads and UI behavior are reported as browser tests. Collision event navigation could not be tested because the packaged runtime reports PYTHIA8/DELPHES unavailable. Rust is also unavailable in the shipped worker's capability response.

The existing executable was tested without rebuilding it. The repository already contained substantial uncommitted changes. No production implementation files were modified for this audit.

## Prioritized findings

### 1. P1 — Conservation badges can pass a failed calculation

**Confirmed shared UI defect; tested with explicit fault injection.**

`src/heplab/server/static/workbench.js:117` labels the analytic energy ledger `Passed` unconditionally. The generator conservation badge uses the same pattern at line 114.

Reproduction: run the bench while a browser test intercepts its completed job response and changes each reported energy residual to **0.5 GeV**. Open Capabilities / checks. The row reads:

> Event energy ledger — Passed — 5.000e-1 GeV residual

This injected value is **not an observed engine result**. Normal runs returned residuals around `1.97e-15 GeV`. The injection demonstrates that the badge has no numerical acceptance criterion. A green badge cannot be used as evidence that the returned result satisfies conservation.

Fix: define and record the applicable absolute/relative tolerances, evaluate the residual and finiteness against them, and display pass/fail/unknown. Keep numerical conservation separate from experimental validation. Verify both passing and failing payloads. The generator case is source-confirmed; its live collision path was not exercised.

Evidence: [fault-injection screenshot](../../output/playwright/desktop-audit-false-pass-injected.png), [structured browser evidence](../../output/desktop-audit/browser-edge-evidence.json).

### 2. P1 workflow gap — Saved work cannot be reopened through the desktop

**Confirmed native session behavior, browser refresh behavior, and source inspection.**

Completed artifacts remain on disk, but a new desktop session starts with no run history. A browser refresh similarly reduced two visible runs to zero. `sessionRuns` exists only in memory (`workbench.js:9`). The worker already exposes `runs.list` and `runs.get`; the interface does not use them. There is also a Save setup command with no corresponding Load setup command.

This is not deletion of scientific data. It is a missing recovery workflow: a researcher cannot return the next day and resume an earlier result or saved parameter set through the application.

Fix: expose persisted runs, reopen their complete metadata/result, and add validated setup import. Include clear handling of incompatible setup/result versions. Treat this as a prerequisite for a research workspace.

### 3. P2 — Recalling a result leaves a different configuration in the form

**Reproduced in the shared browser UI.**

Run at 45 GeV, change to 20 GeV and run again, then select the earlier run. The table and inspector return to 45 GeV while the editable momentum stays at 20 GeV. `workbench.js:395` calls `show()` without restoring the form. A subsequent Run uses the 20 GeV form.

At normal width, the app warns `Parameters modified · run required`; this mitigates the problem. At the supported minimum width of 1100 px, the stylesheet hides `.modified`, removing that warning. At that size, the window can show COMPLETED results with controls belonging to another configuration and no visible stale-result warning.

Fix: distinguish immutable result parameters from a draft configuration, provide an explicit “Use this run's settings” action, and keep the stale-result state visible at every supported desktop size. Show useful run labels such as momentum, seed, model, and timestamp alongside IDs.

Evidence: [45 GeV result / 20 GeV form](../../output/playwright/desktop-audit-history-mismatch.png), [minimum window](../../output/playwright/desktop-audit-minimum-size.png).

### 4. P2 — DY response calculation has almost no visible output

**Confirmed in both the source implementation and shipped worker.**

At seed 42, switching from Ideal to DY reference response leaves every displayed trajectory and digit identical. That is consistent with the intentionally separate truth-to-object response branch, rather than a failure to compute it. However, the particle table continues to show the input momentum; the inspector shows acceptance and efficiency but omits the sampled momentum, scale, and resolution.

For one muon, the optional branch returned a momentum magnitude of approximately **45.418345 GeV/c**, while the main table still showed **45.000**. A researcher changing “Tracking response” receives too little feedback to understand what changed.

Fix: name the branch explicitly, show truth and sampled reconstructed kinematics, efficiency/loss state, and the fit's domain. Provide a corresponding overlay or comparison table. Preserve the current separation from transport/digitization so response is not applied twice.

Code: `workbench.py:190–226`; `workbench.js:336` and the analytic particle-table rendering at line 353.

### 5. P2 — “Input validation: In range” can precede a backend rejection

**Reproduced in the shared UI and shipped worker.**

Select DY reference response and set momentum to 1 GeV. The capability report says **In range**, because it checks individual HTML constraints only (`workbench.js:105`). Run is enabled. Submission then fails with the backend rule requiring momentum >=5 GeV. The user receives a raw Pydantic validation message in the log rather than an error beside the response/momentum inputs.

Fix: mirror the relevant cross-field constraints in the form and report the violated condition next to the input. Keep server validation authoritative. After a failed attempt, explicitly identify any still-visible/exportable result as the previous successful run.

Evidence: [browser validation failure](../../output/playwright/desktop-audit-validation-failure.png), `incompatible_config_capability` and `failed_log` in [browser evidence](../../output/desktop-audit/browser-controls-evidence.json).

### 6. P2 — An unavailable collision mode looks like a dead Run button

**Packaged runtime state confirmed; UI behavior reproduced in browser with the same availability state.**

The shipped worker reports both Rust and PYTHIA8/DELPHES unavailable. Rust is disabled, but the Drell–Yan simulation remains selectable. Selecting it changes the title and properties, then disables Run. The reason is available in a separate capability report, with an environment-variable instruction that is not an actionable desktop installation flow.

This explains one class of apparently non-working buttons. The disabled Run is intentional; the weak part is how the limitation is communicated. Event Previous/Next are also intentionally disabled for the single-event analytic fixture.

Fix: display availability and its reason beside the simulation selector, clearly mark unavailable modes, and provide a concrete setup/help route. Ensure the title and previous result cannot imply that a collision event was just computed.

Evidence: [unavailable collision selection](../../output/playwright/desktop-audit-unavailable-collision.png), `session` in [worker evidence](../../output/desktop-audit/worker-evidence.json).

### 7. P2 — Bench exports lack enough identity for a durable scientific record

**Confirmed by exported JSON inspection.**

The bench export contains its parameters, geometry hash, and material reference, which is useful. It does not contain the desktop job ID, application/worker version, source revision, or creation time. Every bench result suggests the filename `heplab-event-0.json`; every setup suggests `heplab-setup.json`. The exported configuration also contains `events: 100` while the analytic fixture actually produces one event, so the distinction between requested budget and effective event count should be explicit.

Fix: include a versioned artifact envelope with run ID, software/build identity, model/reference hashes, timestamp, requested/effective configuration, and validation scope. Include the run ID in filenames. Keep this finding scoped to the bench export, rather than assuming other analysis artifacts have the same omissions.

Code: `workbench.js:158–164`; analytic result construction in `workbench.py:229–255`. Evidence: [exported event](../../output/playwright/desktop-audit-event.json).

## Physics assessment

The bounded numerical experiment behaved sensibly in the tested cases. At the default settings, each muon deposits about **0.550793 MeV** in 1 mm of silicon; the channels digitize to 55 and 54 ADC. Repeating the same seed reproduces the result exactly. Doubling thickness doubles the modeled continuous deposit, increasing thickness to 5 mm saturates both channels, and raising the threshold to 100 ADC suppresses both. The tested zero-field initial trajectory is straight. The ideal 45 GeV transverse track has an expected curvature radius near 39.5 m at 3.8 T, so its weak visual bending is reasonable.

The silicon radiation length in the app agrees with the [PDG silicon material reference](https://pdg.lbl.gov/2025/AtomicNuclearProperties/HTML/silicon_Si.html). The mean-loss model is based on a frozen [PDG muon stopping-power table](https://pdg.lbl.gov/2025/AtomicNuclearProperties/MUE/muE_silicon_Si.txt). Agreement with a reference table and small energy residuals are useful numerical checks; they do not establish calibrated CMS detector response.

The limitations are mostly stated honestly: two declared back-to-back muons, a single illustrative slab, approximate scattering, predicted crossings, and display outlines rather than a complete material/conditions model. No evidence from this audit establishes collision-generator validation or experimental detector calibration.

From a particle-physics analysis perspective, the desktop still lacks the user workflows needed to load a dataset, define selections, inspect cutflows and weighted histograms, fit a mass spectrum with uncertainties, vary systematics, and compare data with simulation. These may exist elsewhere in the repository; they are not exposed by the desktop interface tested here. The attractive CMS display does not supply those analysis capabilities.

## Release recommendation

Suitable now: an explicitly educational reference bench and demonstration of local simulation plumbing.

Before a research pilot: fix the false pass badges; implement recovery/import of saved work; make result versus draft configuration unambiguous; expose the optional response output; improve validation and unavailable-engine feedback; add durable export identity. Then perform native end-to-end acceptance testing of save/open/export, cancellation during a genuine long job, worker failure/restart, and installed application lifecycle.

## Reproduction assets

- [Packaged-worker harness](../../output/desktop-audit/audit_worker.py) and [full worker evidence](../../output/desktop-audit/worker-evidence.json).
- [Browser control exercise](../../output/playwright/desktop-audit-controls.js) and [structured control evidence](../../output/desktop-audit/browser-controls-evidence.json).
- [Browser edge/fault exercise](../../output/playwright/desktop-audit-edge-cases.js) and [structured edge evidence](../../output/desktop-audit/browser-edge-evidence.json).

The browser fault injection modified only the response seen by the isolated test browser. It did not change production source or the persisted physical result. Test response interception was removed afterward.

Audit reference commit: `eb91e368fc708ba3f9d3d018e3ea27b8987458a4`, plus the existing working-tree changes. Because other work was active in the checkout, this report is a snapshot of the files/builds inspected during the session, not a certification of a clean release commit.
