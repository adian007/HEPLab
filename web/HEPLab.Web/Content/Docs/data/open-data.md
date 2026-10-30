HEPLab can inspect recorded CMS NanoAOD and separately generated simulation.
The workbench labels the two populations explicitly and keeps their selection
and normalization information in the saved analysis.

## Recorded data

The checked-in catalog currently includes the 2016G DoubleMuon dataset from
[CERN Open Data record 30522](https://opendata.cern.ch/record/30522). Recorded
events use the published Legacy2016 certification mask and the declared DZ
dimuon trigger. The workbench reports the source, selected event counts,
cutflow, and provenance with each analysis.

## Simulation

The optional PYTHIA8 and DELPHES workflow is a fast simulation chain. It is
useful for teaching and software checks; it is not a full CMS reconstruction
or an experimental calibration. Data and simulation remain separately
labelled in comparisons.

## Limits

The available sample and current selections do not establish detector
calibration or independent validation. See [the analysis workflow](/analysis/workflow/),
[validation evidence](/validation/evidence/), and [known limitations](/project/limitations/)
for the analysis and validation scope.
