# CMS data workspace — 29 October 2026

The desktop opens on **CMS data**. It can analyze the existing local 100,000-event
Run2016G DoubleMuon and 100,000-event UL2016 Drell–Yan NanoAOD extracts, independently
of event generation. This Windows build bundles both extracts and their source
metadata. Builds without the ignored source sample files support local imports.

## Use it

Choose recorded data and simulation, then **Load selected datasets**. **Apply cuts**
can also load them. Change muon pT, leading pT, eta, isolation, mass window, mass
bins, tight ID or the named DZ trigger and apply again. The ROOT-read counter
stays unchanged while arrays remain cached; no generator runs. Four datasets fit
in the cache. A modified source file is rejected rather than silently reused.

The same cuts are applied to both populations. Data always use the bundled
Legacy2016 luminosity certification mask. Opposite-charge muon pairs are ranked
by scalar pT before the mass cut; one candidate per event is retained. Histograms
show invariant mass, leading pT, leading eta and pair pT. The mass plot includes a
data/MC ratio. Both shapes are normalized separately, including flow bins.

**SVG** and **PNG** beside each plot save standalone figures. The three analysis
export buttons save full JSON and selected-event CSV for each population. JSON
contains selection, source and certification hashes, cutflows, signed sums of
weights, sums of squared weights, normalized covariance matrices and flow bins.
CSV preserves event identifiers as decimal strings. Exports save to Downloads
on this Windows installation. **Reopen last analysis** restores the last immutable
result after restart; applying new cuts loads its underlying datasets as needed.

**Import ROOT** accepts a local compatible NanoAOD projection, classified as data
or MC. It copies bytes through bounded IPC chunks, checks the ROOT schema and
measurement values, and registers the local SHA256 identity. It supports files
up to 512 MiB / 250,000 events and a 256 MiB selected-branch read budget. The
required branches are listed in `src/heplab/server/data_workspace.py`; MC also
requires `genWeight`. Imports remain local. The workflow currently targets the
2016 dimuon schema and certification, not arbitrary ROOT formats or eras.

## Scientific scope

This is an exploratory shape comparison. It has statistical uncertainty and
propagates the correlations from normalization. It does not yet apply luminosity
normalization, cross sections, trigger/ID scale factors, pileup weights, momentum
calibration, background subtraction or systematic variations. It is not a
publication-ready measurement. The provided extracts cover only the first
100,000 entries of each source file. Their local hashes are verified; the full
remote source checksums were not verified, as declared in their metadata.

CMS selections provide aggregate plots, event-row exports and a selected-real-event
3D navigator. Additional channels, multi-file datasets and larger streamed analyses
remain future work.

## Validation

Focused tests cover certification, signed weights, normalized covariance,
candidate ordering, cached cut changes, empty selections, immutable reopening,
bounded imports, invalid ROOT rollback, changed-file rejection, HTTP token
protection and the shared desktop operation table.

The frozen worker, with Python/HEPLab environment overrides removed, loads both
bundled samples and selects 10,863 data / 11,430 MC events with default cuts.
Changing minimum pT to 30 GeV and leading pT to 40 GeV selects 6,678 / 6,981,
with exactly two ROOT reads. Its paginated CSV export contains 10,863 data rows.
Evidence is under `output/cms-data-workspace/`.

Browser UI checks exercise load/apply, stale-cut feedback, tighter and empty
selections, reopening after reload, actual ROOT-file import and reanalysis,
and PNG/SVG/JSON/data CSV/MC CSV downloads. Native desktop checks and build
identities are recorded separately in that evidence directory.

Saved analyses: use the Saved analyses button to browse all stored results, newest first, in pages of 25. Each entry shows its timestamp, dataset names, cuts and selected counts. Open restores the immutable result without re-reading ROOT files. Corrupt or incomplete saved records are omitted.

Native saved-browser acceptance: final rebuilt app restarted, listed all four existing analyses, and opened the oldest c377fe65 result with 15/25 GeV cuts and 10,863 data / 11,430 MC selected events, all four plots and cutflow. The imported ROOT dataset remained available. 27 focused Python tests passed.

Real event display: open any CMS analysis and choose Browse selected real events in 3D. Previous/next and the zero-based event index navigate only its selected recorded events. Run/lumi/event identifiers remain decimal strings. All reconstructed muons in that event are shown, including muons outside the pair selection. Trajectories assume the origin at the interaction point in an ideal 3.8 T solenoid; displayed crossings are predictions. No measured hits, jets or calorimeter deposits are available in these extracts. Source hashes and event identities are checked when reopening the underlying ROOT file. Event export saves JSON including identity and analysis ID.
