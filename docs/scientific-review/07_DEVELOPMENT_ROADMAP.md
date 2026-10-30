# 07 — Scientific Development Roadmap

## Planning principle

Develop evidence before model complexity. The project has limited personal-computer
resources and budget, so the roadmap keeps the current Python reference path, Rust
kernel and pinned fast-simulation path. Full Geant4/CMSSW integration is a distinct
long-term decision with significant setup and conditions-management costs.

## Implementation checkpoint — 30 October 2026

Mass-independent candidate selection, an event-disjoint same-file holdout, centralized
sourced muon constants, isolated lifetime survival, grouped run configuration,
versioned run/event artifacts, the scoped verification registry, typed UI selection,
and canonical site/evidence examples are implemented. The low-mass held-out report
is deliberately a **failed reference regression** because Υ(2S) misses its unchanged
gate. The same-file split does not establish independent-dataset validation.

## Near term — make current claims defensible (0–2 months)

| Priority | Work | Measurable exit criterion |
|---|---|---|
| **Done; evidence gate failed** | Remove target-mass selection leakage and freeze a holdout. | Candidate selection takes no reference mass; train/held-out event IDs and provenance are frozen; old result is exploratory. The new aggregate gate fails at Υ(2S), and same-file events are not an independent dataset. |
| **Done** | Centralize sourced physical constants and attach model/domain metadata. | PDG 2025 muon mass/lifetime and exact SI `c` sources are recorded; run specs name IDs, units, domains, evidence and limitations. |
| **Done** | Add independent calculations and a machine-readable verification registry. | One command reports invariant mass, ideal helix, DOP853 field integration, lifetime, geometry, slab ledger, table domain and RNG checks with scope limits. |
| **Done; isolated** | Add relativistic muon survival using analytic probability and seeded proper-time draws. | Fixed-momentum vacuum model, Wilson interval, altitude-to-path mode and domain tests exist; it is not coupled to track transport or an atmospheric shower. |
| **Done** | Improve model naming and evidence labels in UI/export. | Preflight, typed inspector and exported scopes expose model IDs, units and limitations. |
| **Done for source and contracts; deployment open** | Repair edit paths and declare a canonical site. | ASP.NET source, route/source checks and static fixture files are canonical; public deployment/hosting still requires owner and environment evidence. |
| **Done** | Add a structured first Workbench experiment and demo material. | The site lesson gives an expected curvature value and downloadable v2 setup/result; the artifact is visibly synthetic and reproducible from the repository tool. |

## Medium term — validate model families (2–6 months)

| Priority | Work | Scientific model and success criterion |
|---|---|---|
| **Implemented for numerical domain** | OAE RK4 integration comparison | Independent SciPy DOP853 comparisons cover 18 momentum/η/charge combinations plus an outward boundary-stop check. The comparisons share the pinned OAE function; measured-field and run-era accuracy remain unestablished. |
| **Done for bounded teaching models** | Magnetic curvature/sagitta sweep | Exact uniform-field results cover four momenta, four field strengths and both charge signs; all 32 sagittae agree with an independently evaluated circle formula. Eight bounded OAE reference rows report differences without a measurement-accuracy gate. |
| **Blocked externally for tails** | Material-response benchmark | Mean loss reproduces the PDG table; geometry and slab ledgers are independently checked. Distribution tails require a pinned Geant4 reference or published material-specific measurement and expert-set gates. |
| **Scoped transfer exists; broader coverage open** | Response model coverage | Fixed-seed PYTHIA8/DELPHES DY transfer checks exist; broader process, pT-local, pileup and systematic coverage is not established. |
| **Blocked externally** | Matched data/MC analysis and corrections | Requires certified matched CMS data/MC, trigger and correction payloads, conditions, covariance/systematics and physics review. |
| **Implemented for current views and summaries** | Synchronized views and comparison tool | Linked XY/XZ panels are the default; pointer/keyboard selection and the path cursor are shared. Switchable single XY/XZ and 3D remain available. Comparison JSON records available artifact digests, seeds, models and config differences; plots expose population, binning, event-level statistical errors and omitted systematics. |
| **Blocked on human evidence** | Usability/accessibility evaluation | Requires students/instructors and keyboard/screen-reader workflows on packaged Windows builds; source checks are not user-study evidence. |
| **Implemented for current scope** | Result schema v2 and curated gallery | Full-run/event-view schemas and gallery include synthetic, PDG-table and recorded-data tiers with visible provenance and limits. Independent CMS validation remains open. |

## Longer term — choose a transport research direction (6–18 months)

| Priority | Candidate capability | Model, feasibility and gate |
|---|---|---|
| **P2 — core implemented, scope bounded** | Educational atmospheric-muon survival | A one-muon fixed-momentum survival experiment accepts production/detector altitude under plane-parallel geometry below 75°. Atmospheric density, air energy loss, production spectrum/showers and measurements remain future work. Do not call the current mode a cosmic-ray simulation. |
| **Implemented for the stated software scope** | Magnetic-field teaching experiments | The generated sweep compares exact helix/sagitta over $p_T$, $q$ and $B$ and reports the bounded pinned OAE field reference. It does not establish field measurements or run-era conditions. |
| **P2** | Material energy-loss experiment | Show mean Bethe stopping and a separately sampled straggling model; compare silicon thickness and energy against PDG and a Geant4 reference. Gate: mean, width, tail and energy transfer per thickness. |
| **P3** | Pixel hit/digitization prototype | Start from a declared sensor slab/thickness and simple pitch/threshold model. Do not use CMS module geometry until actual material, Lorentz drift, charge sharing, noise and conditions are included. Gate: comparison to public detector-response measurements or a frozen Geant4/CMSSW fixture. |
| **P3** | Detailed CMS transport | Optional CMSSW/Geant4-backed workflow with run-era GlobalTag, geometry, field IOV and digitization. High setup and compute cost. Gate: clean install/run on supported machine, configuration/data era pinned, conditions IOV resolved, and independent validation across geometry boundaries/material/response. |
| **P3** | Larger event production and uncertainty ensemble | Use batch-friendly formats, sample-level statistics, systematic nuisance variations and distributed compute only after profiling. Gate: uncertainty closure and performance improvement measured on the target laptop. |

## Scientific feature prioritization

| Feature | Scientific/educational value | Current state | Complexity | Priority |
|---|---|---|---|---|
| Relativistic kinematics and time dilation | High; directly demonstrates why fast muons survive longer in lab frame | Four-vector/time-of-flight and separate fixed-momentum vacuum lifetime survival exist; decay is not coupled to transport | Low for analytic survival, medium for sampled decays | P1 complete for isolated experiment |
| Atmospheric muon survival | High; connects proper lifetime, Lorentz factor and path length | Plane-parallel altitude-to-path is available for one fixed-momentum muon; no atmosphere or shower | Medium for one-muon survival; very high for cosmic-ray shower | P2, staged |
| Silicon mean energy loss | High for particle–matter interaction basics | PDG table interpolation already present | Low to improve display; medium to add distribution | P1/P2 |
| Scattering through material | Medium/high; connects radiation length and transverse broadening | Gaussian Highland core present in bounded slab | Medium to compare tails | P1 verification, then P2 |
| CMS tracker field and curvature | High; familiar detector context | OAE tracker field and ideal field present | Medium for independent geometry/field validation | P1 verification |
| Detector response/digitization | High only when channel response is grounded in detector data | Illustrative ADC and separate DELPHES object response | Medium for educational prototype; high for CMS calibration | P2/P3 |
| Monte Carlo collision generation | High for HEP analysis | PYTHIA8→DELPHES DY→μμ present | Low for examples; higher for systematics/full generator coverage | P2 |
| Published-data comparison | Highest scientific credibility value | Run2016G measured references and fits exist; calibration blocked | Medium/high due matching corrections and systematic model | P1 |

All equations above are established physics models. User-interface templates, sample
provenance cards and result-sharing formats are software concepts. They are not novel
physical discoveries or research hypotheses.

## External evidence and product decisions still required

| Blocked item | Precise dependency | Next step when available |
|---|---|---|
| Independent CMS resonance and detector validation | Certified, matched CMS data and MC; identical triggers/selections; corrections and covariance/systematic model; physics reviewer. The current same-file holdout and failed Υ(2S) gate do not satisfy this. | Freeze source ranges, candidate selection, correction versions and final untouched sample before rerunning; publish all gates even on failure. |
| Material-loss tails and straggling | Pinned Geant4 version/physics list and matched material/particle/thickness fixture, or a suitable published distribution with uncertainties; expert-approved thresholds. | Build and hash the fixture, select gates before looking at the holdout, then compare mean, width and tails separately. |
| Run-era CMS transport | Supported CMSSW/Geant4 runtime, resolved GlobalTag and IOV, geometry/material/field conditions and data access. | Resolve and record era conditions, add boundary/navigation checks, then compare with an independent transport reference. |
| Pixel response | Sensor thickness, pitch, noise, thresholds, Lorentz drift, charge sharing and independent sensor response evidence. | Start only from a public or pinned response fixture; retain explicit “illustrative” status until held-out evidence passes. |
| Packaged accessibility and usability | Windows packaged builds, assistive technologies and willing student/instructor participants. | Observe setup→run→interpret→export tasks and record failures and interpretation errors; do not infer outcomes from static checks. |
| Public site deployment | Product decision naming the hosting environment, deployment owner and runtime support policy for the ASP.NET Core 10 app. | Choose and document the target; verify a clean publish and production route smoke test there. |

