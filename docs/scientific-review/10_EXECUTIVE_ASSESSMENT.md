# 10 — Executive Evaluation

## Assessment

HEPLab is an early-stage high-energy-physics workbench with a promising, transparent
engineering base and several useful scientific teaching calculations. Its desktop
analytic mode is a **simplified phenomenological educational simulator**. It can
reproduce selected kinematic, ideal-field and PDG-table calculations quantitatively
within a stated model domain. The repository also provides a separate PYTHIA8→DELPHES
fast-simulation path and selected CMS Open Data analyses. The whole system has not
been validated as a detector simulator or research transport engine.

It is not a quantum-mechanics simulator: no spin state, quantum evolution or weak
decay amplitude is modeled. A separate fixed-momentum vacuum survival experiment is
implemented, but it is not coupled to the analytic track and does not model
atmospheric production. Its CMS field is a pinned, bounded tracker
parametrization, and its displayed crossings are predictions rather than measured
hits. Material handling is one slab with mean loss, Gaussian scattering core and
illustrative electronics. Full material transport, straggling, secondaries, detector
conditions and calibrated response remain outside the implemented bench.

## Strengths

- Transparent separation between Python reference calculations and selected Rust
  kernels, with strict boundaries and targeted parity tests.
- Explicit model maturity and unvalidated states in the code and user-facing result
  paths.
- Strong foundations for seeded reproducibility, immutable artifacts, source hashes,
  local offline HTML export and data provenance.
- Analytic ideal-field trajectory and relativistic four-vector operations are
  inspectable and independently checked against closed forms; the new curvature
  sweep spans charge, momentum and field and compares sagitta with a separate circle
  formula.
- Silicon mean-stopping interpolation has a frozen source and held-out table check;
  CMS field translation has a large pinned software-reference comparison.
- The Workbench and website distinguish synthetic samples, measured CMS data,
  predictions and calibration limitations more clearly than many early prototypes.

## Critical weaknesses

1. The P0 target-mass selection leak is corrected. V2 selects the highest scalar
   $p_T$ opposite-charge pair and splits events before fitting. Its aggregate held-out
   gate **fails at Υ(2S)** under the retained threshold; the holdout is from the same
   source file and is not independent-dataset validation.
2. The isolated muon survival experiment is implemented and scoped. Atmospheric
   production, shower development, air material, energy loss and decay daughters are
   still absent.
3. The analytic detector is not a detector transport model: no complete field,
   run-era conditions, material navigation, stochastic energy loss, secondaries,
   hit formation or data-derived channel calibration.
4. The repository's CMS measured-data result is a data target and regression input;
   its own artifact says detector calibration is blocked pending equivalent selected
   MC and era-matched corrections.
5. Typed selection, preflight, legend, keyboard/table alternatives, reduced-motion
   status, zoom and renderer fallback are implemented. A packaged screen-reader,
   text-scaling and task-based usability review has not been completed with users.
6. The current checkout remains dirty. The ASP.NET Core application is now the
   canonical site source and `/site` is an ignored generated artifact; public
   deployment and clean-release readiness remain unverified.

## Highest-priority actions

| Priority | Action | Why it comes first |
|---|---|---|
| **Implemented; validation result fails** | Remove target leakage, split before fitting, preserve the legacy report and publish corrected v2. | Selection is mass-independent; Υ(2S) gate fails, and same-file events are not independent-dataset evidence. |
| **Implemented for current models** | Version model/provenance records with constants, units, domains, sources and scope. | Current run, event-view, export and display paths identify their evidence boundaries. |
| **Implemented as a separate experiment** | Add analytic/seeded muon survival and altitude-to-path mode. | Fixed-momentum vacuum scope is verified; atmospheric matter and shower remain absent. |
| **Implemented boundary; external work remains** | Keep Geant4/CMSSW separate and distinguish the bench, fast simulation, software references and recorded CMS data. | Labels preserve these categories; full transport and matched data/MC require external conditions and evidence. |
| **Implemented in code; human study open** | Improve typed selection, preflight, comparisons and accessibility behavior. | UI paths and fallbacks exist; packaged assistive-technology and task evidence remains open. |
| **Implemented for source and examples** | Canonicalize the guide and add offline/static evidence examples with provenance. | ASP.NET source contract and examples exist; hosting/deployment target still needs an owner. |

## Readiness for a university demonstration

**Ready for a carefully framed educational demonstration, with limitations stated
up front.** Demonstrate the relativistic four-vector, ideal-solenoid bend, separate
survival experiment, one-slab illustration, reproducible seed and evidence-status
panel. Explain that the CMS field comparison is software-reference evidence and the
silicon check is mean-table reproduction. If showing the corrected low-mass CMS
regression, report its failed Υ(2S) gate and same-file holdout. Do not call the
analytic bench a quantum simulator, atmospheric muon simulator or full CMS detector
simulation.

The professor should be invited to advise which educational experiment and
independent reference should be prioritized. The lifetime teaching core exists; the
next scientific milestone is matched CMS data/MC with corrections and systematics,
plus an independently sourced material/field validation plan.

## Evidence reviewed

Source audit covered project README and handbooks; Python physics, analysis, data,
workbench, export and simulation modules; Rust kernels and Tauri supervisor; the
canonical ASP.NET content/rendering code; project validation records; and relevant
tests. Numerical checks, focused/full software suites, Rust tests and local site
builds are recorded in the implementation checklist. Human-factor studies, external
physics review, clean-machine installation and production deployment remain open.

See [01 — Project Technical Overview](01_PROJECT_OVERVIEW.md),
[02 — Scientific Accuracy](02_PHYSICS_VALIDATION.md) and
[09 — References](09_REFERENCES.md).
