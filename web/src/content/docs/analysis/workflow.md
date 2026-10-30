---
title: Analysis workflow
description: The current path from source records and simulation output to reproducible analysis artifacts.
---

The current analysis increment centers on dimuon events. Data and simulated records pass through shared event contracts and processors where their fields and provenance support that operation.

## Typical local workflow

1. Select a registered dataset or a documented generator configuration.
2. Check source manifest, certification, and backend capabilities.
3. Run the analysis with an explicit input and output path.
4. Inspect cutflows, histogram bins, fitted values, and validation state.
5. Preserve the output with its source ranges, software lineage, configuration, and seed.

Example commands:

```sh
heplab catalog list
heplab run dimuon --input events.json --output artifacts/dimuon.json
heplab plot artifacts/dimuon.json
```

The current JSON input is schema-v1 events (or an object containing an `events` list); NanoAOD ROOT input is also supported by the analysis installation. Plotting writes a PNG. A fit uses the optional CPU `iminuit` backend.

## Weight and artifact semantics

Signed event weights feed yields and cutflows. Variances use the recorded event structure; fitted outputs retain fit and input provenance. Comparison operations require compatible axes and data kinds, and unsupported cases reject instead of silently normalizing away their meaning.

See [analysis and statistical requirements](https://github.com/adian007/HEPLab/tree/main/docs/engineering) before interpreting a result as a physics measurement.
