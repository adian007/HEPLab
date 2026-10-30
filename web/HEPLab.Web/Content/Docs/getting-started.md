---
title: Getting started
description: Install HEPLab and start the local workbench or analysis command line.
---

HEPLab requires Python 3.12 or newer. The guide runs as an ASP.NET Core web app; simulator execution remains in the separate local Python workbench.

## Install the project

From a checkout of the repository:

```sh
python -m pip install -e '.[analysis,serve]'
```

This installs the local GUI/API and the analysis dependencies. You can use the package without the optional analysis stack for core CLI work.

## Open the workbench

```sh
heplab gui --open-browser
```

On Windows, the supported project launcher configures the available WSL runtimes before opening the workbench:

```powershell
.\tools\start_workbench.ps1
```

The workbench shows which engines are available on the current machine. The reference bench is portable. PYTHIA8 and DELPHES require the pinned Linux/WSL runtime; the project does not distribute native Windows or macOS simulation binaries.

For a first local experiment, choose **Magnetic bending bench**, **Muon survival experiment**, or **Silicon mean loss and channel bench** from the starter cards. These use synthetic or declared inputs. The lifetime card opens the separate fixed-momentum survival form; its altitude option is straight-path geometry only. Save setup exports the versioned grouped configuration. Review the model scope before running and export a result to inspect its provenance offline.

## Use the analysis CLI

```sh
heplab version
heplab catalog list
heplab run dimuon --input events.json --output artifacts/dimuon.json
heplab plot artifacts/dimuon.json
```

The dimuon command accepts schema-v1 JSON events or NanoAOD ROOT input. Outputs include cutflows, histogram bins, selected pair masses, and provenance. Read [the analysis workflow](/analysis/workflow/) before interpreting a result.

## First CERN Open Data record

The repository includes a versioned manifest for the [Run2016G DoubleMuon record 30522](https://opendata.cern.ch/record/30522). The manifest records the source, certification, requested entry range, checksums, and provenance. Fetching remote data requires network access; analysis and cached replay are local.

See [the Open Data path](/data/open-data/) for certification and cache behavior.

## Optional native simulation runtime

The pinned PYTHIA8/DELPHES chain is supported on Linux x86-64 and through WSL on Windows. It requires the project runtime lock and local micromamba setup. Follow the [native runtime and acceptance guide](https://github.com/adian007/HEPLab/blob/main/docs/engineering/sim-runtime.md); do not substitute unpinned generator or detector packages when reproducing a recorded run.

## Verify your environment

```sh
heplab sim doctor
```

The doctor reports available engines and runtimes. Missing optional runtimes are reported as unavailable rather than silently substituted.
