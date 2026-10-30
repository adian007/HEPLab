# 03 — Numerical Methods and Verification

## Numerical path in the source

| Operation | Method | Numerical controls and limitations |
|---|---|---|
| Four-vectors and invariant mass | Python binary64 / Rust `f64`; Cartesian metric (+,−,−,−) | Finite checks, physical-mass roundoff tolerance and stable `hypot`; no arbitrary-precision mode |
| Uniform solenoid | Closed-form helix; series expansion for small bend angle | No stepping error in the ideal-field trajectory; fixed momentum and vacuum assumptions |
| Surface crossing | Analytic line/circle intersections with finite-cylinder and annular-disk bounds | 1 nm path/spatial tolerance; sampled polyline for CMS OAE tracker crossings is display-only |
| CMS tracker OAE field | Classical RK4 in path length (s) over position and momentum | Requested step 1–10 mm, bounded by curvature; halves trial step near the validity surface; renormalizes momentum and rejects relative drift ≥10⁻⁷ |
| Material response | One declared thin slab; deterministic mean loss plus addressed Gaussian scattering | Bounds on particle species, $\beta\gamma$, loss fraction, radiation-length fraction and small-angle domain |
| Stochastic draws | SHA-256 of canonical versioned event/object/stage address; open-interval uniform, Box–Muller normal | Independent of iteration order if the address is stable; cross-language encoding and version must be preserved |
| Histogram | Weighted bin accumulation with `sumw`, `sumw²`, flow bins and event-level variance in analysis | Signed MC weights retained; fit support is narrower than the full weighted histogram support |

Key implementations: [reference.py](../../src/heplab/physics/reference.py#L39),
[cms_field.py](../../src/heplab/physics/cms_field.py#L75),
[detector.py](../../src/heplab/physics/detector.py#L145),
[material.py](../../src/heplab/physics/material.py#L11),
[random.rs](../../kernels/physics-core/src/random.rs#L18) and
[dimuon/run.py](../../src/heplab/analyses/dimuon/run.py#L130).

## Independent verification run

The review-only script is
[`verification/independent_checks.py`](verification/independent_checks.py). It does
not change the production code. It was executed using the repository virtual
environment on Python 3.13.14 with SciPy 1.17.1. The script independently computes
closed-form values and compares selected outputs; it is deliberately not called a
full scientific validation.

| Check | Expected result / criterion | Observed result | Interpretation |
|---|---|---|---|
| Back-to-back 45 GeV/c muons | $M=2\sqrt{p^2+m^2}=90.00024808178$ GeV; difference ≤2×10⁻¹² GeV | Difference 0 in binary64 output | Pass for invariant-mass arithmetic and declared mass |
| 45 GeV/c muon in $B_z=3.8$ T for 1 m | $R=39.50101127$ m; independently calculated circular-arc position agrees ≤2×10⁻¹³ m | $\mathbf x=(0.9998931884,-0.0126572278,0)$ m; $E$ and $|p|$ unchanged | Pass for ideal uniform-field formula and sign convention |
| Curvature/sagitta sweep | 32 exact uniform-field cases span $p=1,5,20,100$ GeV/c, $B=0,2,3.8,5$ T and both charges; independent circle formula residual ≤2×10⁻¹² m | All 32 pass; eight pinned OAE cases report endpoint deltas from exact 3.8 T, with maximum 1.836×10⁻³ m | Pass for analytic sagitta arithmetic. OAE deltas have no measurement threshold and do not establish CMS field accuracy |
| CMS tracker field, 20 GeV/c track for 1 m | 5 mm RK4 endpoint vs independently integrated SciPy DOP853, $rtol=10^{-13}, atol=10^{-14}, max\_step=2.5$ mm; difference ≤10⁻¹⁰ m | Difference 8.67×10⁻¹⁶ m; momentum drift 2.22×10⁻¹⁶ | Pass for this ODE integration case; shares the same field parametrization, so does not validate the field source |
| CMS OAE numerical domain grid | 18 combinations: $p=1,20,100$ GeV/c; $\eta=-2.2,0,2.2$; both charge signs; RK4 vs DOP853 ≤10⁻¹⁰ m | Maximum endpoint difference 3.30×10⁻¹² m; outward boundary probe rejected after a bounded stop at 0.0131303 m | Pass for signed transport and stopping at the code domain edge; same field function, not a field-measurement comparison |
| RK4 step halving, 10, 5, 2.5 mm | Stable endpoint under halving | Differences 1.48×10⁻¹⁵ m then 9.31×10⁻¹⁶ m | At roundoff; cannot estimate truncation order from these values |
| PDG silicon mean-loss interpolation at $T=44.8945$ GeV | Independent multiplication of table interpolation by 1 mm; compare to the frozen held-out table gate (2%) | 0.550792855 MeV deposit; held-out max relative error 0.410525% | Pass for table interpolation, not single-event energy-loss physics |
| Addressed uniform RNG | Repeat same address exactly; for 10,000 draws, mean within 0.015 of 0.5 and sample variance within 0.003 of 1/12 | Mean 0.498722; variance 0.081433; same address repeats exactly | Pass as a bounded smoke/statistical check, not a battery or independence proof |
| Muon lifetime survival experiment (separate from bench transport) | $\lambda=\beta\gamma c\tau$, $P_{surv}(L)=e^{-L/\lambda}$ for fixed momentum | Analytic and seeded proper-time modes are implemented; at 1 GeV/c and 15 m decay probability is 0.24034% | Checks the isolated vacuum survival law; no atmospheric production, shower, air loss, scattering or daughters |
| Straight geometry intersections | Independent straight-line roots for finite cylinder and annular disk | Cylinder 1.666667 m; disk 2.5 m; both match closed forms within 2×10⁻¹⁴ m | Software geometry check only; not surveyed detector geometry or hit validation |
| Thin silicon slab bookkeeping | Independently derive continuous mean-loss ledger, outgoing on-shell momentum and Highland core width | Energy residual ≤2×10⁻¹⁵ GeV; digitizer receives the same deposit without modifying transport | Arithmetic consistency only; not straggling, secondaries, recoil or detector calibration |

Re-run the independent calculations and registry from the repository root with:

```powershell
.\.venv\Scripts\python.exe docs\scientific-review\verification\independent_checks.py
.\.venv\Scripts\python.exe tools\run_verification_registry.py
python tools\build_curvature_sweep.py
```

## Existing automated evidence inspected

Targeted coverage exists in `tests/test_physics_reference.py` (closed-form mass,
boosts, random streams and ideal helix), `tests/test_material_and_workbench.py`
(material arithmetic and sampled statistics), `tests/test_trajectory_parity.py`
(Python/Rust parity and invalid domains), `tests/test_cms_physics_validation.py`
(frozen resonance regression), `tests/test_collision_workbench.py` (analysis and
runtime behavior), and `tests/test_education_and_sharing.py` (exports and lab
fixtures). Rust unit tests also cover core operations.

These tests can detect implementation regressions. Two language implementations that
share the same equation can still share the same mistake. The named-reference field
and PDG table checks provide separate comparisons for those domains. The added
straight-geometry and material-ledger checks are analytic/software checks and do not
establish measured detector response. Full-suite status is recorded in
[`IMPLEMENTATION_CHECKLIST.md`](IMPLEMENTATION_CHECKLIST.md).

The checked-in CMS field report records 1,000,000 field reference rows and 14,867
tracker rows; max difference is 1.416 μT against a 2 μT gate. The checked-in silicon
calibration record reports the 0.410525% held-out maximum. Both have narrower scope
than experimental detector validation.

## Required verification matrix before a scientific release

| Experiment | Procedure | Proposed pass/fail criterion |
|---|---|---|
| Four-vector identities | Generate deterministic on-shell vectors; test $E^2-p^2=m^2$, boost then inverse boost, and independently formed invariant masses | Relative residual ≤$10^{-12}$ over declared scale range; report failures and scale boundary |
| Uniform field | Compare analytic helix against independent high-order ODE solver; reverse charge and field signs; test the $B\to0$ line limit | Position difference ≤$10^{-9}$ m for a frozen fixture; energy and $|p|$ conserved to ≤$10^{-12}$ relative |
| Surface intersections | Analytic tangencies, near-origin starts, repeated turns and just-outside bounds; compare to an independent root finder | Root path residual ≤(10^{-8}) m; complete crossing count matches fixtures |
| OAE field integrator | Compare RK4 with SciPy DOP853 across low/high momentum, eta, charge, near-boundary and long paths; vary max step by 2× | Error decreases under halving until roundoff; set separate position/momentum limits before calibration use |
| Material slab | Independently calculate energy from $E_{out}=E_{in}-S\ell$, recompute on-shell momentum, test zero-thickness and rejection bounds | Energy residual ≤$10^{-12}$ GeV in supported range; no claim about recoil or full conservation |
| Sampling | At fixed seeds, test exact replay, schedule invariance, stage decorrelation, distribution moments, tails and Python/Rust canonical-address fixtures | Seed replay exact; distribution intervals predeclared at ≥5σ or exact binomial/normal confidence criteria |
| Stopping-power table | Freeze source hash; train and hold out independent rows; add interpolation edge and monotonicity checks | Existing 2% table gate retained only if chosen before calibration and all source rows/domains are verified |
| Response transfer | Independent training/validation seeds, fixed detector card, bin efficiency/resolution/tail checks, then compare with matched CMS data | Gates predeclared per observable and uncertainty; never treat DELPHES self-closure as CMS calibration |
| Histogram/fit | Compare weighted bin contents and event-level `sumw2`; injection studies for bias/coverage under the exact weighted likelihood | Do not quote fit uncertainty until model, weights, background, and coverage are validated |

No universal percent-level detector tolerance is appropriate without a sourced
dataset, conditions and physics reviewer agreement.

## Statistical and reproducibility gaps

The dimuon analysis retains signed event weights, `sumw`, `sumw2` and event-level
correlated variance. The general unbinned Gaussian-plus-uniform teaching fit rejects
non-unit weights and marks its result `unvalidated`; fit coverage, background model,
FSR and detector systematics remain separate work. The share-v2 HTML exporter now
records result/run/event scope, digests, source file hashes when available, model IDs,
units, settings, seeds, HEPLab/Python/backend/generator versions, the DELPHES card hash
when present, evidence scope/references and privacy flags. The verification registry
records named source hashes, command, environment, thresholds, observations and
`not_established` limits. These fields improve reproducibility but do not prove
correctness. Exact source-tree snapshots, dependency-lock and native-runtime/card
versions for every execution path remain requirements for a release-quality manifest.

See [09 — Scientific References](09_REFERENCES.md) for the PDG, Geant4 and SciPy
references supporting these methods.
