# 09 — Scientific References

The first-party sources below support equations, physical constants, detector and
software scope, numerical methods, and scientific interface recommendations. A
reference is not evidence that HEPLab itself implements or validates the referenced
physics; the scope of each local comparison is stated in the review documents.

## Particle properties, matter and atmospheric muons

### R1

**Particle Data Group, “Muon” particle listing (2025 update).** Mass
$105.6583755\pm0.0000023$ MeV and mean life
$(2.1969811\pm0.0000022)\times10^{-6}$ s. Supports the mass and proper lifetime
used by the centralized constants module and separate lifetime experiment.

[PDG 2025 muon listing PDF](https://pdg.lbl.gov/2025/listings/rpp2025-list-muon.pdf)

The exact SI value of the speed of light used for unit conversions is sourced from
NIST/CODATA; see [NIST constant c](https://physics.nist.gov/cgi-bin/cuu/Value?c).

### R2

**Particle Data Group, “Passage of Particles Through Matter,” Review of Particle
Physics 2025.** Supports the Bethe mean stopping-power context, distinction between
mean and most-probable energy loss, Landau/Vavilov fluctuations and multiple-scattering
tails. The review explains why a Gaussian core and continuous mean loss are not a
full detector material-response model.

[PDG 2025 review PDF](https://pdg.lbl.gov/2025/reviews/rpp2025-rev-passage-particles-matter.pdf)

### R3

**Particle Data Group, muon energy-loss table for silicon.** Frozen data source for
the repository's interpolation; supports only muon mean stopping power in silicon
over the listed kinetic-energy domain.

[PDG muon-in-silicon table](https://pdg.lbl.gov/2025/AtomicNuclearProperties/MUE/muE_silicon_Si.txt)

### R4

**Particle Data Group, “Cosmic Rays,” Review of Particle Physics 2025.** Supports the
distinction between atmospheric muon production as part of hadronic shower
development and a one-particle lifetime survival demonstration.

[PDG 2025 cosmic-ray review PDF](https://pdg.lbl.gov/2025/reviews/rpp2025-rev-cosmic-rays.pdf)

## CMS detector, field and public data

### R5

**CMS Software, pinned CMSSW `BCyl.h` source.** This is the explicit software
reference from which the local CMS tracker OAE field parametrization is ported. The
repository's numerical comparison is a software regression against the pinned
implementation, not new field measurement.

[CMSSW source at pinned commit](https://github.com/cms-sw/cmssw/blob/c04fa510bb587b8ee3fa171888468f80de714fa8/MagneticField/ParametrizedEngine/src/BCyl.h)

### R6

**Karimäki et al., CMS Pixel Detector technical description (2014).** Describes the
original three-layer barrel and two endcap disks used for the guide-surface dimensions
in the project.

[CMS Pixel Detector paper (CERN repository)](https://repository.cern/records/78ehr-0t540/files/TS2013_029_2_2.pdf?download=1)

### R7

**CMS Collaboration, Detector Overview.** General detector context for the inner
solenoid, tracker/calorimeters and outer muon system. It supports the reason a single
uniform bore cannot represent the full CMS field/material structure.

[CMS detector overview](https://cms.cern/news/detector-overview)

### R8

**CERN Open Data Portal, CMS condition database guide.** Explains Global Tags as
coherent sets of records, including alignment and calibration, defined by data-taking
period. Supports the requirement to resolve era/run conditions before full CMS
transport or calibration claims.

[CMS condition database guide](https://opendata.cern.ch/docs/cms-guide-for-condition-database)

### R9

**CMS Collaboration, Run2016G DoubleMuon NanoAOD record (record 30522).** Source and
citation record for a measured-data path; states run range, dataset format, validated
run requirements and data processing conditions. It does not endorse derived HEPLab
results.

[CERN Open Data record 30522](https://opendata.cern.ch/record/30522)

## Simulation software and numerical method

### R10

**Geant4 Physics Reference Manual 11.4.** Authoritative description of mean energy
loss, material-dependent ionization, multiple scattering, fluctuations and transport
processes. Supports the recommendation to compare against a pinned Geant4 setup if
detailed transport is pursued; it does not make Geant4 output a substitute for
experiment-specific validation.

[Geant4 Physics Reference Manual PDF](https://geant4.web.cern.ch/documentation/dev/prm_pdf/PhysicsReferenceManual.pdf),
[mean energy loss](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/energy_loss/enloss.html),
[energy-loss fluctuations](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/energy_loss/fluctuations.html),
[multiple scattering](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/elastic_scattering/msc.html)

### R11

**Delphes project documentation.** Describes Delphes as a fast generic collider
detector-response simulation with tracking, calorimeter and muon-system components.
Supports the “fast simulation” label for the local PYTHIA8→DELPHES route.

[Delphes](https://delphes.github.io/)

### R12

**Bierlich et al., “A comprehensive guide to the physics and usage of PYTHIA 8.3,”
SciPost Physics Codebases 2022.** Primary reference for PYTHIA8 event-generation
settings, process configuration, tune and generator interpretation.

[PYTHIA 8.3 guide, arXiv:2203.11601](https://arxiv.org/abs/2203.11601),
[official manual index](https://pythia.org/documentation/)

### R13

**SciPy documentation, `solve_ivp` / DOP853.** Describes DOP853 as an eighth-order
explicit Runge–Kutta solver recommended for high-precision non-stiff IVPs. Used in
the review script as a different integrator for one short CMS-field ODE comparison;
the field function remains the same pinned local parametrization.

[SciPy `solve_ivp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html),
[SciPy DOP853](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.DOP853.html)

## Scientific visualization and accessibility

### R14

**ROOT TEve Event Display documentation.** Describes ROOT's experiment-independent
event visualization environment, used for event visualization and debugging. Supports
recommendations for typed object selection and linked event inspection.

[ROOT TEve](https://root.cern/doc/master/group__TEve.html),
[TEve selection](https://root.cern/doc/master/classTEveSelection.html)

### R15

**ParaView Users Guide and selection-link API.** Supports multi-view inspection,
explicit selections and linked-view interaction as established scientific
visualization patterns.

[ParaView Users Guide](https://docs.paraview.org/en/latest/UsersGuide/),
[linked selection API](https://www.paraview.org/paraview-docs/v6.0.0/cxx/classvtkSMSelectionLink.html)

### R16

**W3C Web Content Accessibility Guidelines 2.2.** Relevant criteria include keyboard
access, visible focus, reflow and non-text contrast. Use as a content/web baseline;
it is not a complete audit of a packaged native desktop application.

[WCAG 2.2](https://www.w3.org/TR/WCAG22/)

## Local evidence and implementation sources

- [Physics reference](../../src/heplab/physics/reference.py), [detector geometry and intersections](../../src/heplab/physics/detector.py), [CMS tracker field](../../src/heplab/physics/cms_field.py), [material model](../../src/heplab/physics/material.py).
- [Silicon table calibration](../../src/heplab/physics/calibration.py), [field evidence JSON](../../src/heplab/data/reference/cms-field-validation.json), [silicon evidence JSON](../../src/heplab/data/reference/silicon-calibration.json), [muon response evidence JSON](../../src/heplab/data/reference/muon-response-calibration.json).
- [PYTHIA8/DELPHES adapter](../../src/heplab/sim/pipeline.py), [Workbench](../../src/heplab/server/workbench.py), [scientific review verification script](verification/independent_checks.py).
- [CMS resonance evidence scope and limitations](../engineering/cms-physics-regression.md), [field/geometry/calibration open gates](../engineering/geometry-calibration.md), [verification strategy](../engineering/14-verification.md).

