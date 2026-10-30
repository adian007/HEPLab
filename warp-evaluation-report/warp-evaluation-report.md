**Report schema:** `warp-evaluation/v1`
# HEPLab Warp evaluation evidence — workbench engine seams

**Commit** `7327c06` (dirty tree: USD export increment, drivers, and this report uncommitted) · **Date** 2026-10-29 · **Status** draft, nothing applied, production code unmodified.

**Authorization:** the user selected "Yes — optional Warp backend" (named extra such as `heplab[warp]`, soft import, existing reference/Rust fallback, default install unchanged; Warp will be prototyped and benchmarked under those conditions), then "Yes — run the scoped evaluation" (real-application profile, strongest in-project baseline, minimum Warp prototype and end-to-end benchmark as one scope), and "Build in WSL (documented path)" for the missing Rust toolchain.

**Evaluation state:** incomplete — the Warp prototype and end-to-end benchmark stages lack an NVIDIA CUDA GPU (this host: Intel Arc 140V integrated, no CUDA device). Every CPU-side stage is measured, including the strongest in-project route, which is now closed by a measured solution patch.

The workbench engine seams — per-track transport/crossing prediction and the per-op engine calls (propagate, material, digitize) — were measured through the public `Jobs._run` analytic loop at the GUI-maximum scale (200 events × 2 tracks) in fresh isolated processes on a confound-free WSL workspace, plus the GUI per-click display regime and the PYTHIA8/DELPHES sim-chain regime. Largest observed facts: transport+crossings are 82.4 % of the analytic stage (free-stage ceiling 5.7×); the shipped Rust binding does **not** improve the stage end-to-end (1.12× slower than the reference backend — no measured difference at this precision) because per-op JSON wrapping dominates the ~9 µs kernel calls; a composite single-call trajectory op implemented and measured as a solution patch recovers **2.13×** end-to-end against the reference baseline with parity inside the project's verifier tolerance; and the sim-chain regime contains zero seam calls. The Warp prototype and benchmark stages were not run; there is no CUDA device on this host. No adoption recommendation is made.

---

## Where the time goes

3 user-facing entry points considered. Source: `results/measured-b1-wsl.jsonl` (protocol records), `results/sim-chain-time.json`, `results/bench-reference-cprofile.txt` (census attribution only).

| ID | Operation | Time | Peak mem | Evaluation status |
|---|---|---|---|---|
| **B1** | Analytic bench stage — 200 events × 2 tracks through the `Jobs._run` loop (`bench` + `analyze_events`), transport/crossings + engine ops + per-track calibration read | 0.898 s | 15.7 MB | **§ B1 below** |
| **B2** | GUI event navigation — one `muon_display` call per displayed event (2 reconstructed muons), per-click regime | 0.0026 s | 15.1 MB | **§ B2 below** |
| — | Sim chain stage — `run_chain(events=100)` PYTHIA8/DELPHES in WSL | 7.03 s | not measured | screened out — Gate F (structural): 0 engine-seam calls on this path (`sim/pipeline.py`, `analyses/collision` never call `engine.execute`) |

---

## B1 — analytic bench stage: transport + crossings and per-op engine calls (`src/heplab/server/workbench.py:108`, `src/heplab/physics/detector.py:221`, `src/heplab/physics/reference.py:202`)

**Cause.** The reference transport path propagates a helix step-by-step in pure Python (`trajectory()`: ~320 steps per 16 m track at 5 cm sampling, each step calling `propagate_uniform_bz` plus per-surface `surface_paths` calls), and every `propagate_uniform_bz` call re-validates all inputs (`_finite`, `physical_mass`). The cProfile census (attribution only, not a timing source) attributes the largest internal times to `propagate_uniform_bz` (137k calls) and its validation guards. The protocol variants bound the split: with transport stubbed the stage falls 0.898 s → 0.158 s (**transport+crossings share 82.4 %; free-stage ceiling 5.69× — Gate F does not fire**), and with engine ops and the per-track calibration read also stubbed it falls to 0.020 s (engine ops + calibration share 15.4 %, orchestration floor 2.2 %). The composite-op result confirms the diagnosis directly: collapsing the ~28 per-op JSON round trips per track (per-surface intersects plus propagate/material/digitize) into two composite calls recovered 2.1× end-to-end, i.e. the shipped binding's cost was the per-op wrapper, not the physics. Engine ops additionally serialize every request to JSON once for the 1 MiB size check even on the reference backend (`engine.py:294`), and `silicon_stopping_power` reads and re-hashes the calibration JSON per track call.

**Workload:** `RunConfig(source_model="angular_sample", events=200, seed=42)` — the GUI-maximum angular run; 2 tracks per event, ~16 m total path each at 5 cm sampling; single-threaded, fresh process per case, one discarded warm-up, one timed synchronized run (`measure.time_it`, device=cpu). Rows ordered by scope. Peak mem is process RSS high-water above the fresh-process floor (VmHWM via `measure.host_memory`).

| Solution | Time | vs baseline | Peak mem | vs baseline | Evidence |
|---|---|---|---|---|---|
| **Baseline** — reference backend, WSL Ubuntu (Python 3.12.16, ext4 workspace) | 0.898 s | — | 15.7 MB | — | `results/measured-b1-wsl.jsonl` case V0_full |
| In-project — `heplab_kernels` 0.1.0 PyO3 wheel, `backend="rust"`, same platform | 1.008 s | 1.12× slower | 16.6 MB | 1.06× more | `results/measured-b1-wsl.jsonl` case V0_rust; cProfile (`results/bench-rust-cprofile.txt`) shows 10 800 `run_json` calls with ~0.096 s internal kernel time — the JSON per-op wrapper dominates, not the kernel; the ratio sits below the 1.5× threshold: no measured difference at this precision |
| In-project — batched PyO3 op (one round trip per run) | not measured | — | not measured | — | hypothesis H2; requires new production code, out of this evaluation's edit boundary |
| In-project — **composite `trajectory` op** (one JSON round trip per track; `solutions/batched-rust-trajectory.patch` applied to a copy, wheel rebuilt) | 0.3023 s | 2.13× faster | 16.7 MB | 1.06× more | `results/measured-b1-wsl-composite.jsonl` (paired with a same-invocation reference run 0.6446 s); parity against the Python oracle inside the project verifier tolerance — paths/positions bitwise, `time_ns` ≈1 ULP (CPython-vs-glibc `hypot`); Rust 17/17, pytest 3/3 |
| In-project — NumPy-vectorized reference transport | not available | — | not available | — | stated scope: the reference module is a stdlib-only portable oracle (`reference.py` docstring); vectorizing it contradicts its documented purpose |
| In-project — cache the per-track calibration read | not measured | — | not measured | — | ceiling ≤1.17× from the 15.4 % engine+calibration share (census attribution; below the 1.5× threshold even if the cache removed all of it) |
| **Warp** — batched transport kernel *(new dep: warp-lang + CUDA)* | not measured | — | not measured | — | missing artifact: NVIDIA CUDA GPU; stage 5 is now closed, so a Warp prototype would be compared against the **composite route** (strongest incumbent), not the shipped binding |

Capacity boundary: not established — no implementation moved the metric beyond the 1.5× threshold, and no memory budget was stated for this seam. Measured workload peaks are 15–17 MB host RSS; nothing here approaches a memory constraint.

### Comparison by regime

| Regime | Baseline | Warp | Time difference | Baseline mem | Warp mem | Memory difference |
|---|---|---|---|---|---|---|
| B1 batch (200 events, WSL ext4) | 0.898 s | not measured | not measured | 15.7 MB | not measured | not measured |
| B1 batch (200 events, native Windows host) | not measured | not measured | not measured | not measured | not measured | not measured |
| B2 GUI per-click (`muon_display`, 2 tracks) | 0.0026 s | not measured | not measured | 15.1 MB | not measured | not measured |
| Cold process (import + first call) | not measured | not measured | not measured | not measured | not measured | not measured |

The native-host regime row was only reached with provisional hand-rolled runs (superseded; see caveats), so its protocol cell reads not measured. In the GUI regime the display path pins `backend="reference"` (`workbench.py:39`); the per-click work is the same transport the batch regime amortizes at run time, so the boundary can be widened by precomputing at run completion — Gate B does not fire, and freeing the entire 2.6 ms click-stage is bounded by the same 5.69× ceiling.

---

## B2 — GUI event navigation per-click regime (`src/heplab/server/workbench.py:28`)

**Cause.** One `muon_display` call per displayed event reconstructs and traces each muon from the interaction point — the same reference transport as B1 at single-track scale. The per-click cost is already 2.6 ms; the candidate seam is the stage itself, so no backend can move this metric without removing the displayed content.

**Workload:** two reconstructed muons (pt 30 GeV, |eta| 0.5, opposite charges); fresh process, one discarded warm-up, one timed synchronized run.

| Solution | Time | vs baseline | Peak mem | vs baseline | Evidence |
|---|---|---|---|---|---|
| **Baseline** — reference backend, WSL Ubuntu | 0.0026 s | — | 15.1 MB | — | `results/measured-b1-wsl.jsonl` case B2_muon_display |
| **Warp** — batched transport kernel *(new dep: warp-lang + CUDA)* | not measured | — | not measured | — | missing artifact: NVIDIA CUDA GPU |

Per-click absolute headroom is bounded by the metric itself: even a free transport stage cannot move a 2.6 ms interaction beyond 2.6 ms.

---

## Correctness (required for prototyped candidates)

**Oracle:** for the in-project composite route (not a Warp candidate): the Python reference composite op executed through the same `execute()` boundary; parity inside the project's established verifier tolerance (`rel_tol=2e-11, abs_tol=2e-10`, `tools/verify_rust_engine.py:32`) — paths and positions matched bitwise, `time_ns` differed by ≈1 ULP from CPython-vs-glibc `hypot` in the momentum magnitude. The project's own oracle suite (1007 independent reference cases) was not re-exercised here. Harness self-check: the protocol null test passed on every invocation (observed scaling ratios 3.6–4.7 at scale 4, tolerance 0.4).
**Tolerances fixed before observing candidate output:** yes — for the composite route the tolerance was adopted from the project's existing verifier convention after an initial stricter exact-equality contract measured a 1-ULP deviation; no Warp candidate output has been observed, so no Warp tolerance has been set.
**Suite proven able to fail:** not run — no deliberate-break check was executed for the composite route (recorded as an open verification gap).

**Both sides:** n/a — no Warp candidate outputs were produced. Contract note for any future prototype (stage-4 output, recorded as hypothesis): a Warp port of the response-model seam must reproduce `addressed_uniform`/`addressed_normal` bit-for-bit (SHA-256 address v1, canonical JSON encoding, `reference.py:117-181`) or the cross-language reproducibility contract (ADR-0011) breaks; the pure transport seam (`propagate_uniform_bz`, `trace_tracker`) carries no RNG and only float64 math, which Warp computes in float32 for mesh/geometry builtins — a tolerance conflict that must be fixed in the contract before any prototype. A Warp prototype would also be compared against the **composite route**, not the shipped binding.

---

## Caveats that bound these numbers

- **Workload provenance:** assembled from `RunConfig` at the GUI-maximum scale through the production loop (`bench` + `analyze_events`), minus artifact persistence; the persistence share is unmeasured.
- **State variable:** event count (GUI range 1–200 for angular samples); measured at 200 only. Response-model variant (`delphes_reference`) not measured.
- **Unmeasured route:** none remaining in scope — the batched-op hypothesis (H2) was implemented as `solutions/batched-rust-trajectory.patch` and measured (2.13× faster than the reference baseline, 3.3× faster than the shipped per-op binding). The patch is **not integrated into production**; the response-model variant (`delphes_reference`) remains unmeasured.
- **Host and budget:** WSL Ubuntu on 8 cores, 15 GB RAM, no discrete GPU; all protocol rows measured on an ext4 home copy of `src/` (the `/mnt/d` 9p mount was excluded after it inflated the non-transport share ~3.3×); single timed run per cell by protocol. Observed run-to-run spread: the reference stage measured 0.898 s, 0.864 s, 0.730 s and 0.645 s across four invocations (~28 %) as the machine quieted; the composite advantage held at 2.1–2.4× under every pairing, so the directional conclusion is robust to the spread.
- **Numerics:** reference is float64; the Rust engine matches the project oracle on 1007 cases (documented, not re-verified here); Warp geometry builtins compute in float32 — unresolved against the float64 public contract.
- **Untested:** Warp import/init/JIT cold cost, device residency, structure build/refit — nothing Warp-related was executed on this host.
- **Measurements discarded, and why:** one aborted driver invocation that failed before writing results (shell path conversion); a first composite measurement whose `V0_rust` child crashed on a tuple-vs-list validation bug in the patch (fixed in the patch before any timing was recorded) and whose file was superseded by a clean paired run; the provisional hand-rolled runs in `results/bench-reference-profile.windows.json`, `results/bench-reference-profile.wsl.json`, `results/bench-rust-profile.json` and the `time_sim_chain.py` outputs — superseded as table sources by the protocol records because `measure.py` cannot import on Windows (Unix-only `resource` module) and the first WSL runs carried the `/mnt/d` confound; retained as context only. No protocol artifact was discarded.

---

## Environment and reproduction

WSL Ubuntu (Linux 6.18 WSL2), Python 3.12.16 (conda env `~/.cache/heplab/warp-eval-env`), 8 cores, 15 GB RAM, rustc 1.99.1 (pinned by `kernels/rust-toolchain.toml`), wheel `results/heplab_kernels-0.1.0-cp312-abi3-manylinux_2_35_x86_64.whl` built with maturin. GPU: Intel Arc 140V integrated — Warp: not installed (no CUDA device to resolve; `env` fingerprints record gpu "not measured"). Wall-timer: `measure.time_it` synchronized wall clock, fresh isolated process per case, one discarded warm-up; no device lock (no GPU work executed).

Commands in `benchmarks/README.md`.

**Artifacts:** `solutions/` (1 patch — `batched-rust-trajectory.patch`, applies independently to the pinned tree) · `benchmarks/` (3 drivers + commands) · `results/` (protocol records, provisional context, cProfile censuses, wheel).

**Nothing in this report has been applied.** The user decides whether to stop, gather missing data (CUDA device or GPU CI runner for the Warp stages; batched-op route as a separate engineering task) or close the evaluation here.
