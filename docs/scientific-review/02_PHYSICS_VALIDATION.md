# 02 — Scientific Accuracy Assessment

## Overall finding

The current Workbench combines exact special-relativistic kinematics, an exact
vacuum helix in a uniform axial magnetic field, a bounded RK4 transport through one
pinned tracker-field parametrization, and simplified material/electronics models.
These pieces must not be collapsed into a single “physics accurate” label. The
engine itself declares a low-fidelity analytic/thin-slab scope and the material and
object response outputs are marked educational and unvalidated. A separate fixed-
momentum proper-time survival experiment is available; atmospheric shower production
and transport remain outside the implementation.

The best-supported classification is **simplified phenomenological educational
simulation**, with a few calculations that are correct within explicit domains and
separate reference regressions. It is not a quantum-mechanical simulation. The muon
spin-½ quantum number is not propagated; the engine uses classical relativistic
four-vectors, Lorentz-force trajectories and stochastic draws. No quantum state,
spin precession, weak decay amplitude, neutrino final state or $g-2$ evolution is
implemented.

## Implemented models and scientific status

| Process | Governing model and implementation | Status, assumptions and missing physics |
|---|---|---|
| Muon state and invariant mass | $E^2=\mathbf p^2+m^2$ in $c=1$ units; $p_z=p_T\sinh\eta$, $E=\sqrt{p_T^2+p_z^2+m^2}$. `FourVector` uses the (+,−,−,−) metric. | Correct standard kinematics in the supported float64 domain; independently reproduced for a 45 GeV/c back-to-back pair. The muon mass and lifetime are centralized with units, uncertainty, PDG 2025 source and a version ID. [source](../../src/heplab/physics/reference.py), [constants](../../src/heplab/physics/constants.py), [PDG R1](09_REFERENCES.md#r1) |
| Uniform $B_z$ propagation | $d\mathbf p/ds=0.299792458q\,\hat{\mathbf p}\times\mathbf B$, $R=p_T/(0.299792458|q|B)$ metres for $p_T$ in GeV/c and $B$ in tesla. The reference uses the analytic helix with a small-angle series; $t(s)=sE/(pc)$. | Exact for a uniform axial field, fixed momentum, vacuum and no electric field. It conserves $E$, $|p|$, and $p_z$. It does not model decay, material, radiation, spin, field fringe or return field. [source](../../src/heplab/physics/reference.py#L202) |
| CMS tracker-field propagation | OAE parametrization ported from a pinned CMSSW source; vacuum Lorentz ODE integrated by classical RK4, step ≤10 mm and further limited by momentum; stops at $r<1.15\,\mathrm{m}, |z|<2.8\,\mathrm{m}$ boundary. | Implementation regression against 1,000,000 pinned software-reference points passes a 2 μT max-vector gate (observed 1.416 μT; RMS 0.404 μT, 14,867 tracker points). An additional independent ODE integrator grid and charge/momentum/field sagitta comparison check declared software behavior. These checks do not use independent field measurements, establish run-era conditions, or provide full-detector transport. Full map transport is explicitly disabled. [source](../../src/heplab/physics/cms_field.py#L24), [curvature sweep](../../src/heplab/data/reference/curvature-sweep-v1.json), [report](../../src/heplab/data/reference/cms-field-validation.json), [CMSSW R5](09_REFERENCES.md#r5) |
| Geometry and crossings | Analytic intersections with finite cylinders and annular disks for the ideal field; CMS field crossings are found on a 5 mm sampled polyline. | Implemented guide geometry for the original 2009–2016 pixel layout and a few envelopes. A crossing is a predicted geometric surface intersection, not a measured hit or precision navigation. No sensor modules, services, alignment, occupancy or full material map. [source](../../src/heplab/physics/detector.py#L72) |
| Silicon mean ionization | Frozen PDG muon-in-silicon stopping table; log-energy interpolation between alternating training knots. $\Delta E_{mean}=(dE/dx)\,\ell$. | Held-out maximum absolute relative error is 0.410525%, below a predeclared 2% table-reproduction gate over the table domain (kinetic energy 0.1–100 GeV). This is mean stopping power only. It is not a sampled loss spectrum, detector response, or CMS calibration. [source](../../src/heplab/physics/calibration.py#L24), [PDG data R3](09_REFERENCES.md#r3) |
| Thin-slab scattering and transport | Gaussian projected Highland core: $\theta_0=\frac{13.6\,\mathrm{MeV}}{\beta pc}\sqrt{x/X_0}[1+0.038\ln(x/X_0)]$, sampled in two transverse directions; a continuous mean deposit changes the on-shell momentum. | Domain-bounded to heavy singly charged particles, user-declared $\beta\gamma$ range, fractional loss ≤10% kinetic energy, and $0.001≤x/X_0≤0.1$ for scattering. No Molière tails, straggling, δ-rays, bremsstrahlung, pair production, nuclear interactions, recoil bookkeeping or slab geometry navigation. [source](../../src/heplab/physics/material.py#L11), [PDG R2](09_REFERENCES.md#r2), [Geant4 R8](09_REFERENCES.md#r8) |
| Digitization | Analog channel $A=g\Delta E+P+\sigma_n Z$; threshold, clipping/saturation and integer ADC floor. Workbench defaults are hand-set gain/pedestal/noise/threshold/saturation. | Arithmetic is explicit and repeatable by seed; electronics values are illustrative, not a calibrated CMS pixel front-end. A channel threshold is not a validated hit-efficiency model. [source](../../src/heplab/physics/material.py#L95) |
| Object-level response | Bernoulli efficiency and mean-normalized log-normal momentum scale/resolution, with address-derived random values. Optional transfer parameters come from fixed-seed PYTHIA8/DELPHES DY samples. | A scoped software transfer check in $5≤p_T≤200$ GeV, $|\eta|<2.4$, DY mass window 60–120 GeV, no pileup; three eta-bin training/held-out gates pass in the recorded artifact. $p_T$-local dependence, tails, general processes and experimental CMS calibration are unresolved. This branch is separate from the analytic track and does not draw a DELPHES reconstructed trajectory. [source](../../src/heplab/physics/calibration.py#L127), [parameters](../../src/heplab/physics/calibration.py#L251), [report](../../src/heplab/data/reference/muon-response-calibration.json) |
| Collision generation | PYTHIA8 $pp\to\gamma^*/Z$ at configurable $\sqrt{s}=1–14$ TeV, with a generated mass window of 60–120 GeV and Z forced to decay to muons; fixed tune/PDF settings, serial seed; then DELPHES CMS card. | A real event-generator/fast-response chain exists in the supported Linux/WSL runtime. No pileup, no claimed NLO matching and no Geant4 CMS detector simulation. `23:onIfAny=13` forces the Z to muons; it is not a muon-lifetime decay model. [source](../../src/heplab/sim/pipeline.py#L132), [Delphes R9](09_REFERENCES.md#r9), [PYTHIA R10](09_REFERENCES.md#r10) |
| Proper-time survival | A separate experiment samples $s_{decay}=-\beta\gamma c\tau_\mu\ln u$ and compares with $P_{surv}(L)=e^{-L/(\beta\gamma c\tau_\mu)}$. Optional altitude inputs provide a plane-parallel straight path. | Analytic law and seeded sample are checked. At 1 GeV/c, the mean decay path is 6.234 km and decay probability over 15 m is 0.24034%. Momentum is fixed; the altitude option adds geometry only. There is no primary cosmic-ray spectrum, pion/kaon shower, atmospheric energy loss, scattering, or decay chain. [source](../../src/heplab/physics/lifetime.py), [PDG R1](09_REFERENCES.md#r1), [cosmic-ray review R12](09_REFERENCES.md#r12) |

## What counts as validation here

Four levels must remain separate:

1. **Software verification:** unit/property tests, bounds, Python/Rust parity,
   deterministic RNG addresses and IPC contracts.
2. **Named-reference agreement:** such as the PDG mean-stopping table or a pinned
   CMSSW OAE implementation. The claim is limited to the named reference, its
   domain and the tested quantities.
3. **Detector calibration:** fit detector response using appropriate data and
   corrections, with training/held-out separation and uncertainties.
4. **Physics validation:** compare predictions with independent, relevant
   measurements under matched conditions, including uncertainty and model
   limitations.

Current source artifacts support levels 1 and 2 for selected components. A frozen
CMS measured Z target exists, but the corresponding artifact marks detector
calibration blocked pending equivalent selected MC and era-matched corrections.
The selected data sample is not a full detector validation. A code pass or a match to
a PDG mass does not establish level 3 or 4.

## Resonance regression: selection leakage corrected, held-out gate failed

The legacy v1 low-mass sample selected candidates by closeness to PDG target masses.
It is now retained only as `exploratory_target_dependent` and excluded from pass gates.
The v2 builder first selects the opposite-charge pair with the highest scalar-$p_T$
sum, without passing mass or resonance targets to the selector, then assigns a
deterministic event-ID hash split before fitting. The frozen sample uses entries
`[100000, 300000)` from the same Run2016G file and a 20% event-disjoint holdout.
Training and held-out events are disjoint, but this is not an independent dataset or
an experimental detector validation.

The v2 reference regression **fails** its predeclared overall gate: J/ψ, Υ(1S), and
Υ(3S) held-out mass checks pass, while the Υ(2S) held-out mean differs from the
reference by −49.30 MeV against a 30 MeV tolerance. The threshold and fixture were not
changed. The report status is `failed_reference_regression`; the result is not a pass
and does not establish detector calibration. See the [versioned report](../../src/heplab/data/reference/cms-resonance-data-report-v2.json), [selected pairs](../../src/heplab/data/reference/cms-resonance-selected-pairs-v2.json), and [legacy label](../../src/heplab/data/reference/cms-resonance-data-report-target-dependent-legacy.json).

## Recommended corrections and limits

- **P0 implemented:** mass-independent highest-scalar-$p_T$ pair selection,
  event-ID split before fitting, frozen v2 provenance, and regression coverage.
  The same-file holdout does not satisfy an independent-dataset validation claim,
  and the frozen overall gate currently fails at Υ(2S).
- **P1 implemented:** lifetime as a separate, explicit fixed-momentum survival
  experiment with proper-time sampling and a bounded plane-parallel altitude mode.
  It is not a full atmospheric-muon simulation.
- **P1:** keep model/data categories visible in plots and exports: truth, declared
  analytic trajectory, predicted crossing, simulated fast-response object, measured
  NanoAOD object and digitized slab channel are not interchangeable.
- **P1:** version and centralize constants with source/year metadata; set tolerances
  and supported domains per model, not globally.
- **P1:** do not advertise the thin slab as detector transport. Add stochastic loss,
  secondaries and detailed geometry only through an independently validated
  Geant4/CMSSW workflow or a smaller model that passes specified reference tests.

## Reference calculation example

For the bench default $p=45$ GeV/c and $B=3.8$ T, the curvature radius is

\[
R=\frac{45}{0.299792458\times3.8}=39.5010\;\mathrm m.
\]

For the default 1 mm silicon slab, the frozen PDG table interpolates to
$dE/dx=0.550793$ GeV/m at kinetic energy 44.8945 GeV, hence a continuous mean
deposit of 0.550793 MeV. This arithmetic is internally consistent with the table;
the physical single-particle deposit distribution is not represented by that mean.

See [03 — Numerical Methods and Verification](03_NUMERICAL_VERIFICATION.md) for the
reproducible independent script and numerical outputs.
