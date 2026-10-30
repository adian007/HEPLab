# Benchmarks and reproduction

All drivers are read-only with respect to production code. The **protocol
driver** is the authoritative measurement path (imports the warp-eval skill's
`measure.py`; fresh isolated process per case; records carry `env`
fingerprints). The **provisional drivers** predate it and are retained as
context only — `measure.py` cannot import on Windows (Unix-only `resource`
module), so all protocol rows were measured in WSL.

## Protocol driver (authoritative — B1/B2 rows in the report)

The stage is measured on an ext4 copy of `src/` to exclude the `/mnt/d` 9p
confound:

```sh
wsl.exe -e bash -lc 'rm -rf "$HOME/warp-eval-stage"; mkdir -p "$HOME/warp-eval-stage/results"; \
  cp -r /mnt/d/HEPLab/src "$HOME/warp-eval-stage/src"; \
  cp -r /mnt/d/HEPLab/warp-evaluation-report/drivers "$HOME/warp-eval-stage/drivers"; \
  cd "$HOME/warp-eval-stage"; \
  "$HOME/.cache/heplab/warp-eval-env/bin/python" drivers/measure_b1_stage.py . \
  /mnt/c/Users/adian/.zcode/skills/warp-eval/scripts results/measured-b1-wsl.jsonl \
  V0_full V1_no_transport V2_floor V0_rust B2_muon_display'
```

Cases: `V0_full` (baseline reference stage), `V1_no_transport` (transport
stubbed), `V2_floor` (engine ops + calibration stubbed), `V0_rust` (Rust
backend, requires the built wheel in the env), `B2_muon_display` (per-click
regime). A `null_test` harness self-check is emitted automatically.

## Rust wheel build (documented project path, WSL)

```sh
wsl.exe -e bash -lc 'cp -r /mnt/d/HEPLab/kernels "$HOME/heplab-kernels-build" && \
  cd "$HOME/heplab-kernels-build" && source "$HOME/.cargo/env" && \
  "$HOME/.cache/heplab/warp-eval-env/bin/python" -m maturin build --release \
  --out /mnt/d/HEPLab/warp-evaluation-report/results'
```

## Sim-chain regime (provisional wall clock; seams structurally absent)

```sh
PYTHONPATH=src ./.venv/Scripts/python.exe warp-evaluation-report/drivers/time_sim_chain.py D:/HEPLab
```

Requires the pinned sim runtime (`heplab sim doctor` must pass; WSL prefix
`~/.cache/heplab/sim-runtime`).

## Provisional drivers (superseded context)

- `profile_bench.py` — cProfile census + hand-rolled variants (native Windows and WSL).
- `profile_bench_rust.py` — same, with `backend="rust"` (requires the wheel).

Their JSON outputs live in `results/` and are cited in the report only as
context and census attribution, never as table timings.

## Warp stages

Not runnable on this host — no NVIDIA CUDA device. A prototype would additionally
require `warp-lang` behind the agreed optional extra and the stage-4 contract
(noted in the report's correctness section) settled first.

## Composite-route measurement (stage-5 solution)

```sh
wsl.exe -e bash -lc 'cd "$HOME/warp-eval-patched" && \
  git -c core.autocrlf=false apply /mnt/d/HEPLab/warp-evaluation-report/solutions/batched-rust-trajectory.patch && \
  source "$HOME/.cargo/env" && \
  cargo test --locked --manifest-path kernels/physics-core/Cargo.toml && \
  (cd kernels && "$HOME/.cache/heplab/warp-eval-env/bin/python" -m maturin build --release --out ../results/wheel) && \
  "$HOME/.cache/heplab/warp-eval-env/bin/python" -m pip install -q --force-reinstall --no-deps \
    results/wheel/heplab_kernels-0.1.0-cp312-abi3-manylinux_2_35_x86_64.whl && \
  "$HOME/.cache/heplab/warp-eval-env/bin/python" -m pytest tests/test_trajectory_parity.py -q && \
  "$HOME/.cache/heplab/warp-eval-env/bin/python" drivers/measure_b1_stage.py . \
  /mnt/c/Users/adian/.zcode/skills/warp-eval/scripts results/measured-b1-wsl-composite.jsonl V0_full V0_rust'
```

## Warp stages 6–7 runbook (requires an NVIDIA CUDA machine)

See `WARP-STAGES-RUNBOOK.md`. Nothing in the evaluation runs Warp until a CUDA
device resolves; Warp's CPU backend is out of scope by protocol.
