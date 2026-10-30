# Solutions

## batched-rust-trajectory.patch

Composite `trajectory` op: one JSON round trip per track (sampling, field exit,
crossings) instead of ~28 per-op JSON round trips per track through the PyO3 binding.

- Applies independently to the pinned tree (`git apply` from the repository
  root; both Windows-CRLF and WSL working trees verified with
  `git -c core.autocrlf=false apply --check`).
- Contents: `kernels/physics-core/src/trajectory.rs` (new module + unit tests),
  protocol wiring, `engine.py` op table + reference-composite oracle,
  `detector.py` single-call rust path, `tests/test_trajectory_parity.py`.
- Evidence: parity inside the project verifier tolerance (paths/positions
  bitwise; `time_ns` ~1 ULP from CPython-vs-glibc `hypot`); measured 0.3023 s
  vs 0.6446 s paired reference (2.13x faster end-to-end) —
  `../results/measured-b1-wsl-composite.jsonl`.
- Status: **not integrated into production**; integration is a separate
  product decision.

No Warp candidate patch exists: stage 6 requires an NVIDIA CUDA device to
verify Warp resolves CUDA before any prototype code is exercised.
