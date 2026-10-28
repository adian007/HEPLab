# ADR-0010: Polyglot compute strategy — Python shell, Rust kernels, JAX GPU math


> Historical design proposal. Current scope and implementation evidence are defined
> in the [engineering handbook](../engineering/README.md) and ADR-0011.
> The following diagram describes the proposal, not shipped capability.

```mermaid
flowchart LR
    A[Independent CPU reference] --> B[Measured bottleneck]
    B --> C[Validated optional Rust or GPU backend]
    C --> D[Same public contract]
```

- **Status:** Proposed
- **Date:** 2026-10-26

## Context

ADR-0001 chose Python-first for teaching, ecosystem, and installability — and that decision stands for the *interface*. But the goal is also to make the platform computationally serious. HEPLab's real compute hotspots are:

1. **Per-event kernels** in analyses: pair combinatorics (dimuon/diphoton), selection math — today JIT'd via numba inside coffea processors;
2. **Ingest transcoding**: ROOT→parquet conversion, checksums (adler32/sha) over large streams;
3. **Statistics**: unbinned likelihood fits plus *toy-MC systematics ensembles* (thousands of pseudo-experiments) — embarrassingly GPU-parallel;
4. **Toy simulation**: parametrized smearing, event generation glue.

Landscape verified (2026): Rust has real CERN/HEP prior art — [fastPASTA](https://crates.io/crates/fastpasta) (ALICE raw-data scanner) and [alice-rs/root-io](https://github.com/cbourjau/alice-rs) (pure-Rust ROOT binary parsing). Julia has [UnROOT.jl](https://github.com/topics/cern-root) (pure-Julia TTree *and* RNTuple reader) and a maintained [JuliaHEP distribution via CVMFS](https://discourse.julialang.org/t/julia-for-hep-now-available-via-cvmfs/129737), with a [performance study for HEP analyses](https://www.osti.gov/servlets/purl/1797923). GPU/autodiff fitting is production-proven in HEP: [zfit](https://scikit-hep.org/iminuit/notebooks/binned_vs_unbinned.html) (TensorFlow-based, used by LHCb-style analyses) and [JAXFit](https://jaxfit.readthedocs.io) (GPU/TPU nonlinear least squares). [Mojo reached 1.0 in August 2026](https://www.modular.com/blog/modular-26-5-mojo-1-0-is-here) with an Apache-2.0 open-source compiler and source-stability guarantees, but its scientific ecosystem is still young.

## Decision

A **four-tier compute strategy**. The Python API and `pip install heplab` promise (ADR-0001) never change; compiled layers ship as wheels and always have a pure-Python/numba fallback.

**Tier 0 — numba baseline (all kernels start here).** Every kernel is written first as a numba/NumPy reference implementation. This is both the fallback path and the correctness oracle.

**Tier 1 — Rust kernel layer** (`heplab-kernels` crate via PyO3 + maturin) for *profiled* hot paths only:
- ingest transcoding + streaming checksums (memory-safe over untrusted byte streams, no GIL, true parallel chunks);
- jagged combinatorics kernels where numba is clumsy or slow;
- toy-smearing / generation vectorization.
Users never see Rust: maturin wheels install transparently; missing wheel ⇒ numba path.

**Tier 2 — JAX GPU/autodiff backend for the statistics layer.** zfit/iminuit stay the stable API (ADR-0007 unchanged); a JAX backend provides likelihood autodiff, GPU unbinned fits, and large toy-MC systematics ensembles (the dominant compute cost of honest systematics). CPU JAX also accelerates on machines without GPUs.

**Tier 3 — Mojo experimental lane.** One bounded pilot: benchmark a single kernel (pair combinatorics or smearing) against the Rust and numba implementations, CPU and GPU. Mojo is *not* a core dependency; the lane is revisited annually now that 1.0 + open compiler exist.

**Governance rules (what keeps this engineering, not résumé-driven):**
1. *Profile first* — no tier-1 port without a named bottleneck and a benchmark in `tests/bench/`;
2. *Oracle rule* — every compiled kernel is golden-tested against its numba reference on committed event samples;
3. *API freeze* — no compiled language is visible in the Python API, CLI, or notebooks;
4. *Published numbers* — a kernel benchmark table ships in the docs every release.

Phase mapping: Tier 0 exists from P0; Tier 1 starts in P2–P3 (transcode + combinatorics first); Tier 2 lands with the fitting work (P2 core, P4 systematics); Mojo pilot only after P3 closure reports exist to benchmark against.

## Alternatives considered

| Option | Why not |
|---|---|
| Julia as the core kernel language | Strongest runner-up — UnROOT.jl + JuliaHEP are real and the perf paper is convincing. But a second runtime splits codebase, CI, notebooks, and contributor base. Kept as an optional *sandbox container* for numerical prototyping, not a dependency |
| C++ analysis layer | Incumbent and fastest, but worst teaching/maintainability tradeoff; C++ already lives where it belongs — inside the PYTHIA8/DELPHES sim containers |
| Mojo as core | 1.0 + open compiler is a milestone, but the scientific library ecosystem is too young to bet the core on; pilot lane instead |
| Zig / Chapel / OCaml | No HEP ecosystem payoff for this project's size |
| Python + numba only | Safe, but leaves real, measured headroom unused for ingest throughput and systematics-scale toy MC — the two places open-data users actually wait |

## Consequences

- **Positive:** large speedups exactly where users wait (ingest, fits, toy MC); memory safety at the byte-stream boundary; GPU capability without changing the API; a principled, publishable performance story; teaching narrative improves ("see the likelihood's gradients").
- **Negative:** three toolchains to review (Python/Rust/JAX config); maturin wheel matrix per platform; GPU path needs a CPU-equivalent guarantee (JAX CPU backend covers it); benchmark maintenance.
- **Neutral:** ADR-0001 remains fully intact for users; container images grow (Rust toolchain only in builder stages).

## References

- fastPASTA (ALICE, Rust): https://crates.io/crates/fastpasta · alice-rs / root-io: https://github.com/cbourjau/alice-rs
- UnROOT.jl & JuliaHEP: https://discourse.julialang.org/t/julia-for-hep-now-available-via-cvmfs/129737 · https://www.osti.gov/servlets/purl/1797923
- JAXFit: https://jaxfit.readthedocs.io · zfit/iminuit unbinned fits: https://scikit-hep.org/iminuit/notebooks/binned_vs_unbinned.html
- Mojo 1.0 (Aug 2026, Apache-2.0 compiler): https://www.modular.com/blog/modular-26-5-mojo-1-0-is-here
