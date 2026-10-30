---
title: Contributing
description: Set up a checkout, find the canonical requirements, and run the project checks before proposing changes.
---

HEPLab is early-stage research software. Contributions should identify their model domain, units, data provenance, error behavior, and evidence. Start with the [engineering handbook](https://github.com/adian007/HEPLab/blob/main/docs/engineering/README.md) and the [implementation roadmap](https://github.com/adian007/HEPLab/blob/main/docs/engineering/implementation-roadmap.md).

## Development setup

```sh
python -m pip install -e '.[dev,analysis,serve]'
```

For Rust/PyO3 work, follow [`kernels/README.md`](https://github.com/adian007/HEPLab/blob/main/kernels/README.md). For native simulation, use the pinned [Linux/WSL runtime guide](https://github.com/adian007/HEPLab/blob/main/docs/engineering/sim-runtime.md).

## Project site

The public guide is an ASP.NET Core Razor Pages app targeting .NET 10:

```sh
dotnet run --project web/HEPLab.Web
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

Write guide pages in `web/HEPLab.Web/Content/Docs/`. Keep technical claims linked to their canonical engineering record, and distinguish software checks from physics validation.

## Review checks

```sh
python tools/check_handbook.py
python -m pytest
```

Run the relevant focused checks for the code you changed. Do not describe a passing software test as proof of detector calibration or scientific validity.

## Project channels

Use the repository’s [issues](https://github.com/adian007/HEPLab/issues) and [pull requests](https://github.com/adian007/HEPLab/pulls) for technical discussion and review. The project license is Apache-2.0.
