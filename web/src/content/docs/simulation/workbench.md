---
title: Local workbench
description: What the local simulator interface does and how to start it.
---

The HEPLab workbench is served by the local Python application. Its run controls submit jobs to that local process; the public documentation site has no simulation API and cannot access your local files.

## Main work areas

- **Model and source selection:** choose an available reference or native backend and configure its inputs.
- **Run controls:** start or cancel a local job, with supported ranges and prerequisites shown by the application.
- **Event display:** inspect particle paths in XY, XZ, and 3D views, along with geometry surfaces and predicted crossings.
- **Results:** inspect particle properties, diagnostics, validation scope, and exported artifacts.

Camera and visibility controls affect the display only. They do not change simulation data or exported numerical results.

## Start the workbench

```sh
heplab gui --open-browser
```

On Windows, use `tools/start_workbench.ps1` to configure installed WSL runtimes. The desktop shell also uses the local worker process and a bounded set of validated commands; it does not embed the public site.

For exact control and output semantics, read the [GUI design and source review](https://github.com/adian007/HEPLab/blob/main/docs/engineering/gui-design.md).
