# 08 — Professor Presentation Brief

## Suggested title

**HEPLab Workbench: a transparent muon-physics teaching bench and early HEP analysis
workflow**

Avoid calling the current build a quantum simulator or a validated CMS detector
simulation.

## 10–12 minute structure

| Time | Slide / demonstration | Key message |
|---:|---|---|
| 0:45 | Motivation and scope | Explain the project goal: let learners connect muon kinematics, track curvature, a simple material layer and reproducible analysis. Define that the desktop analytic pair is a declared test case. |
| 1:00 | Physical background | Present $E^2=p^2+m_\mu^2$, $R=p_T/(0.299792458|q|B)$, and $P_{surv}=e^{-L/(\beta\gamma c\tau_\mu)}$. The first two are in the analytic Workbench; survival is a separate fixed-momentum vacuum experiment and is not coupled to track transport. |
| 1:00 | Architecture | Show Tauri → Rust supervisor → Python worker → Python/Rust reference engine; separately show PYTHIA8→DELPHES and CMS NanoAOD analysis. Emphasize these are distinct paths. |
| 2:30 | Live demonstration | Run the default 45 GeV/c opposite-charge pair in 3.8 T; show XY/XZ/3D, predicted crossings, material deposit and the event table. Use the reproducible sweep to compare sagitta across charge, momentum and field, then show the bounded OAE software comparison. Show source model, seed, units and validation label. |
| 1:15 | What is verified | Demonstrate invariant mass, uniform-helix closed form and independent circle sagitta formula; show PDG table held-out agreement and pinned CMSSW field software comparison. Explain software/reference checks versus detector calibration. |
| 1:15 | Limitations | Lifetime survival is an isolated experiment; there is no atmospheric production, shower, air material, complete material map, straggling/secondaries, measured hit formation or run-era conditions. The low-mass held-out reference gate currently fails at Υ(2S). |
| 1:00 | Roadmap | Show the completed target-independent selection repair and its failed aggregate gate, the separate lifetime lab, remaining independent numerical/material evidence, and only then a possible Geant4/CMSSW transport mode. |
| 1:00 | Feedback requested | Ask which physics sequence is most pedagogically useful, what accuracy target is appropriate, which reference dataset/model to prioritize, and whether a full-detector route justifies the setup cost. |

## Demonstration preparation

1. Launch the Workbench and use a saved, versioned analytic configuration. Keep the
   standard result preloaded as backup in case native runtime startup is slow.
2. Show the declared source: one back-to-back pair, not generated collision data.
3. Set $p=45$ GeV/c and $B_z=3.8$ T. State expected $R=39.5010$ m and show
   the one-metre bend is approximately 0.02532 rad.
4. Select one muon and show charge, truth momentum, slab deposit, response branch and
   predicted crossings in the inspector/table.
5. Show the result's model status/provenance. Export the current event and open the
   standalone HTML to demonstrate reproducibility and shareability.
6. If time allows, contrast the analytic bench with the PYTHIA8/DELPHES collision
   path and clarify that it is fast simulation, not Geant4 CMS transport.
7. If showing lifetime, open the separate fixed-momentum survival experiment. State
   that its altitude option is plane-parallel path geometry only and that it is not
   coupled to the bench trajectory or an atmospheric shower.
8. If showing the low-mass CMS report, say that candidate choice is target-independent,
   the holdout is disjoint but from one file, and the frozen aggregate gate fails at
   Υ(2S). Do not describe it as independent validation.

## Claims safe to make

- “The Workbench implements checked relativistic four-vectors and an analytic
  uniform-solenoid helix for a declared muon test pair.”
- “A silicon mean-stopping interpolation reproduces held-out PDG table rows within
  the recorded gate; its scattering, digitization and response have narrower scopes.”
- “A fixed CMS tracker-field parametrization is compared with a pinned CMSSW software
  reference over a large point sample. It is not a run-conditioned full-field map.”
- “The repository also contains a scoped DY→μμ PYTHIA8/DELPHES chain and separate
  analysis of CMS Open Data.”
- “The implementation is a simplified educational workbench; detector calibration
  and independent physics validation remain open.”

## Questions for the professor

- Which is the clearest first lesson: curvature, lifetime dilation, energy loss or
  reconstruction response?
- What level of agreement would be meaningful for an undergraduate teaching
  experiment, and which published reference should define it?
- Should the project stay laptop-first and educational, or should it pursue a
  separate CMSSW/Geant4 workflow with greater setup cost?
- Which experiment could provide a genuinely independent check of the model rather
  than a software self-consistency test?
- What uncertainty and model-limit displays would you expect students to interpret?

