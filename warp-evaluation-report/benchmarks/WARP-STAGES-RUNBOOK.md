# Warp stages 6–7 runbook (blocked only on an NVIDIA CUDA device)

Everything preparable without CUDA is done: the evaluation's stage 5 is closed
(the composite route is measured and is the strongest incumbent), the contract
is recorded in the report's correctness section, and the measurement harness is
proven (`measure.py` protocol, null tests pass). What remains is the Warp
prototype and its end-to-end benchmark, which by protocol must run synchronized
on an explicit CUDA device — Warp's CPU backend is out of scope.

## What stage 6 will do (minimum unit)

1. Install `warp-lang` (the agreed optional-extra shape: `heplab[warp]`, soft
   import, reference/composite fallback) and verify
   `wp.get_device("cuda:0").is_cuda` before any other work.
2. Prototype one kernel: **batched sampled transport** — launch over all tracks
   of a run × their sample paths in ONE launch, computing the same closed-form
   uniform-Bz helix step (`propagate_uniform_bz` semantics, float64 math, no
   mesh builtins) as the composite route, with surface crossings computed by
   the same analytic port used in `geometry.rs`.
3. Run the adversarial contract checks from the report's correctness section:
   parity against the Python oracle (project verifier tolerance), deliberate
   break to prove the suite fails, correctness at production scale.

## What stage 7 will do (whole-boundary benchmark)

- Copy `drivers/measure_b1_stage.py` per bottleneck; add a `V0_warp` case whose
  `bench` call routes transport through the Warp seam (integration off by
  default, opt-in flag only).
- Measure through `measure.py` on the CUDA device (synchronized wall clock,
  cold + warm process regimes, `host_memory` + `device_memory`), always against
  the strongest incumbent = the **composite route**, same boundary.
- Transcribe into the report; the evaluation state flips to `complete` only
  when every seam/regime has an end-to-end Warp measurement.

## Time and cost preview

Unknown until a device is available. The prototype is a small CUDA kernel over
≤10⁵ elements; expected wall clock on a T4-class device is minutes per
measurement sweep once the environment installs (`warp-lang` wheels bundle
CUDA). No dataset beyond the existing synthetic bench workload is required.

## Where a CUDA device can come from

- Any NVIDIA GPU workstation/laptop (driver + `warp-lang`).
- A GitHub Actions **larger runner** with GPU (`ubuntu-gpu`-class labels) —
  billed per-minute even for public repositories, so it needs billing enabled
  on the repository owner's account.
- Any cloud GPU VM the user already has credentials for.

After any of these runs, drop the resulting `measured-b1-warp.jsonl` into
`results/`, transcribe the rows, and re-run
`scripts/validate_report_schema.py warp-evaluation-report`.
