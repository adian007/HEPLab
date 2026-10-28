# ADR-0007: iminuit + zfit for fits; pyhf later for template likelihoods


> Historical design proposal. Current scope and implementation evidence are defined
> in the [engineering handbook](../engineering/README.md) and ADR-0011.
> The following diagram describes the proposal, not shipped capability.

```mermaid
flowchart LR
    A[Validated candidates and weights] --> B[Normalized likelihood]
    B --> C[Fit covariance and diagnostics]
    C --> D[Independent coverage checks]
```

- **Status:** Proposed
- **Date:** 2026-10-26

## Context

Analyses need fits: the Z line shape (Voigtian over background), the H→γγ bump hunt (signal over smooth exponential background), and efficiency/turn-on curves. The HEP default (RooFit) drags in ROOT. The platform is Python-first (ADR-0001) and must report both statistical and systematic uncertainties, even if the systematics model is a skeleton in v1.

## Decision

- **Base:** NumPy/SciPy for simple quantities (counts, means, quick checks).
- **Fits:** `zfit` ( likelihood modeling) + `iminuit` (MINUIT2 minimization/uncertainties) for unbinned and binned fits.
- **Later:** `pyhf` for template-based likelihoods when analyses graduate to full signal/background models.
- **Systematics skeleton (v1):** nuisance-style variations of selection efficiency and energy scale, propagated by re-running fits on varied inputs and reporting the spread.

## Alternatives considered

| Option | Why not |
|---|---|
| RooFit / ROOT fitting | Violates no-ROOT-dependency principle (ADR-0001); API not teaching-friendly |
| `scipy.optimize.curve_fit` only | No robust uncertainty/correlation treatment; inadequate for physics claims |
|Full pyhf from day one | Template machinery is overkill for v1 unbinned fits; added later without refactor pain since artifacts/stamps don't change |

## Consequences

- **Positive:** pure-PIP stack; iminuit's asymmetric errors/Hesse matrix give publication-style uncertainty reporting; fits are fast and testable against toy-MC golden values.
- **Negative:** zfit API still evolving (pin versions); systematic treatment in v1 is deliberately simplified and labeled as such.
- **Neutral:** fit configs (model, ranges, initial values) live in analysis YAML, stamped into results.

## References

- zfit, iminuit, pyhf documentation; PDG values used as fit-validation targets
