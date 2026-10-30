---
title: Known limitations
description: Important model, data, validation, and distribution boundaries in the current implementation.
---

## Physics validation

Software checks and named-reference comparisons do not establish CMS detector calibration or broad agreement with measured collision data. Current physics artifacts retain an unvalidated state where independent evidence is not available.

The corrected low-mass resonance regression selects candidates without mass targets and splits events before fitting. Its current aggregate report is a failure because the held-out Υ(2S) mean misses the frozen tolerance. The holdout is event-disjoint within one file/run period and is not an independent dataset.

## Reference bench

The thin-slab bench is a scoped educational reference for heavy, singly charged particles in silicon. It does not include stochastic energy loss, secondaries, showers, a full detector material budget, or complete detector response.

## Detector model

The sourced geometry and reference field checks cover specified dimensions and software reference points. The ideal-solenoid path omits fringe and return-yoke fields. Full field-map transport and validated detector conditions remain unavailable.

The survival exercise uses fixed momentum and a plane-parallel straight path. It is not a full atmospheric-muon or cosmic-ray shower model.

## Native generation

PYTHIA8 and DELPHES run only in the pinned Linux/WSL environment. The fixed-seed integration check is software smoke-test evidence, not an independently validated cross-section prediction. Pileup and NLO matching are not claimed.

## Distribution

The Windows desktop build has been smoke-tested, but there is no public installer. Native simulation binaries are not supplied for Windows or macOS.

Read the engineering handbook for the detailed validity domain and open release gates.
