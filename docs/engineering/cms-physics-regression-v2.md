# CMS resonance reference regression v2

This version supersedes the target-dependent low-mass selection described in
[the historical v1 procedure](cms-physics-regression.md). The old selected pairs
and report remain packaged so earlier artifacts can still be read, but the
report is explicitly marked exploratory and is not eligible for validation
pass gates.

## Current frozen result

The v2 sample is built from entries `[100000, 300000)` of CMS Open Data record
30522, one Run2016G DoubleMuon NanoAOD file. It applies the checked-in certified
run/luminosity sections, the recorded low-mass trigger groups and the stated
muon `pT`/`η` cuts. For each accepted event, the selector chooses one opposite-
charge pair by maximum scalar `pT` sum, with stable pair-order tie-breaking.
The selector receives only the two transverse momenta; it cannot inspect pair
mass, resonance identity, or PDG target values.

After candidate selection, the run/luminosity-block/event identity is hashed by
`sha256-run-lumi-event-mod5-v1`. The five-way split assigns one bucket to
held-out and four to training, before any peak fit. In this same-file slice,
J/ψ has 5,108 training and 1,240 held-out candidate events; the combined Υ
trigger population has 2,048 training and 469 held-out events. The two groups
are event-disjoint. They share the same source file and run period, so this is
not an independent dataset or an experimental detector validation.

The frozen report is
[`cms-resonance-data-report-v2.json`](../../src/heplab/data/reference/cms-resonance-data-report-v2.json)
and its selected-pair input is
[`cms-resonance-selected-pairs-v2.json`](../../src/heplab/data/reference/cms-resonance-selected-pairs-v2.json).
The JSON records source integrity, certification and manifest hashes, selected
pair hash, split and candidate-selection algorithm IDs, environment versions,
and deterministic fit-result digest. The fixture is about 3.9 MB.

The predeclared checks give an overall `failed_reference_regression` result.
J/ψ, Υ(1S) and Υ(3S) held-out reference-mass gates pass; the Υ(2S) held-out
fit is 9.974000 GeV, −49.30 MeV from the 10.023260 GeV reference, exceeding
the existing 30 MeV gate. No threshold or fixture was adjusted to make that
gate pass. The J/ψ eta-bin resolution envelopes and held-out Z template-shape
closure pass their own checks. These results do not calibrate individual muon
momenta or the detector response.

## Reproduce

Run the frozen refit without network access:

```powershell
uv sync --extra analysis --extra dev
uv run python tools/build_cms_resonance_validation.py `
  --from-pairs src/heplab/data/reference/cms-resonance-selected-pairs-v2.json `
  --provenance src/heplab/data/reference/cms-resonance-data-report-v2.json `
  --output-dir artifacts/cms/resonance-validation-v2-replay
uv run python -m pytest tests/test_cms_physics_validation.py -q
```

Regenerate the source slice with the same entry bounds:

```powershell
uv run python tools/build_cms_resonance_validation.py `
  --entry-start 100000 --entries 200000 `
  --output-dir artifacts/cms/resonance-validation-v2
```

The builder verifies the frozen ROOT file size and advertised Adler-32,
applies the bundled certification, selects and splits events before fitting,
and writes `selected-pairs.json` with `validation.json`. Keep those output files
together. Review a refreshed report's exact status; a valid software regression
may fail a scientific reference gate.

## Scope boundaries

- The training/held-out split checks event-level reproducibility within the
  named file and period. It does not supply an independent data-taking period.
- Trigger populations and offline `pT`/`η` cuts still define acceptance; no
  trigger-object matching, acceptance correction or per-muon momentum
  correction is applied.
- The peak regression compares reconstructed data-spectrum means with broad
  reference tolerances. Approximate Gaussian Fisher errors omit background-fit
  uncertainty; the Υ fit has a single Gaussian signal and does not model
  feed-down or detailed line shapes.
- The J/ψ resolution envelopes are broad digitizations from a different CMS
  analysis. The raw Z spectrum has final-state radiation and no Rochester or
  precision-scale correction; the Z template check is shape closure only.
- A pass would be a named reference-data regression. It would not establish a
  Geant4 CMS simulation, measured detector calibration, or general physics
  validation. The current aggregate result is a failure.

The original target-selected report is preserved at
[`cms-resonance-data-report-target-dependent-legacy.json`](../../src/heplab/data/reference/cms-resonance-data-report-target-dependent-legacy.json).
