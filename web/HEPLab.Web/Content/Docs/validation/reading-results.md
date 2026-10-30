---
title: How to read a result
description: Interpret software status, reference agreement, calibration, and physics validation without conflating them.
---

## Four different questions

1. **Did the software execute?** A successful run or regression answers this for a tested code path and configuration.
2. **Did a model match a named reference?** The report must identify the reference, domain, split, and predeclared acceptance gate.
3. **Was a detector response calibrated?** Calibration needs appropriate measured or reference inputs and must preserve its validity domain.
4. **Is the physics prediction validated?** Independent comparisons, uncertainties, and a stated validity domain are needed. A data/MC overlay or smoke test alone is insufficient.

## Read the metadata

For a reproducible record, inspect the source and exact event ranges, certification, software and engine versions, model configuration, random seed, artifact identity, and validation state. A checksum proves that bytes match a recorded digest; it does not establish scientific correctness or authorship.

If a result is marked `unvalidated`, keep that label with downstream plots and summaries. Do not infer stronger evidence from a feature maturity label or a green software check.

The engineering [preservation and trust chapter](https://github.com/adian007/HEPLab/blob/main/docs/engineering/13-preservation-and-trust.md) defines the canonical artifact requirements.
