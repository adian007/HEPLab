# HEPLab project review — 2026-10-30

## Executive summary

HEPLab has a thoughtful scientific-software foundation: explicit data provenance, reference comparisons, immutable result concepts, a useful capability/maturity model, a documented separation between the public site and local simulation, and unusually candid limits on what the current physics models establish. The main risk is that the implementation is growing faster than its independent validation, release automation, and user evidence.

**Production status: not deployed by this review.** The working tree is uncommitted on `codex/desktop-phase0-baseline`. The checked-in automation has no production deployment step. The CI workflow builds and publishes the ASP.NET app into a temporary runner directory; the desktop workflow produces unsigned artifacts for the Actions run and explicitly does not publish a release. No production host, domain, deploy secret/configuration, or Sites project binding was found. The production target is ambiguous: the website is being replaced and the desktop bundles are unsigned. Publishing this state without first identifying the intended host/product could remove the previous Astro site or leave the new server app without a compatible host.

## Scope and evidence

Reviewed repository structure, current Git status and diffs, README and engineering/web handbooks, CI and desktop workflows, desktop worker IPC, Python/Rust physics and material models, resonance-validation code, the workbench and event-display documentation/markup, and the new ASP.NET Razor Pages implementation. Generated build/cache/data outputs were treated as artifacts, not source. No test suite was run for this review.

External references used for physics and interface expectations: [CMS detector overview](https://cms.cern/news/detector-overview), [CMS detector](https://cms.cern/detector), [PDG 2024 passage of particles through matter](https://pdg.lbl.gov/2024/reviews/rpp2024-rev-passage-particles-matter.pdf), and [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## Findings by priority

### P0 — No safe path from this checkout to production

- `.github/workflows/ci.yml` restores/builds/publishes `web/HEPLab.Web`, but its publish output is only `.cache/heplab-web` on the ephemeral CI runner; nothing uploads or deploys it.
- `.github/workflows/desktop.yml` creates unsigned Windows/Linux/macOS packages as temporary Actions artifacts. The workflow says release signing is separate and that it does not publish a release.
- `docs/web/06-delivery-plan.md` lists selecting a .NET 10 host and adding deployment automation as unfinished work.
- The current branch is local and has uncommitted changes. There is no configured production URL or hosting record in this repository. A connected Sites inventory also had no matching site.
- The old Astro source is deleted in the working tree while `web/HEPLab.Web/` is untracked. This is a framework/hosting change, not a routine content update. The new app needs an ASP.NET Core-capable .NET 10 host; a static host cannot serve it as-is.

**Fix:** decide whether “production” means the public guide, desktop installer, or local Workbench; record the current URL/host and owning deploy process; preserve or deliberately migrate existing routes/assets; then add a deploy artifact, environment-specific configuration, post-deploy smoke checks, and rollback procedure. For desktop distribution, add signed/notarized release packaging and a versioned release workflow. Build and acceptance gates must pass before deployment. Do not claim these edits are live until the deployed version is checked at the actual production URL or installed package.

### P1 — Resonance regression selection uses the target mass

`tools/build_cms_resonance_validation.py` builds opposite-charge pair candidates and chooses the pair with minimum distance from the target PDG mass (around lines 166–177). The resulting selected distribution is then used for a mass-closure comparison. The selection therefore uses the reference value that the regression later treats as an independent check; this can sculpt the result toward the target and overstate closure. The method is also described in the generated report metadata.

**Fix:** freeze a mass-independent candidate policy based on muon quality, trigger, vertex and event selection, or use all candidates in a model that handles combinatorics. Select before opening the validation mass window, version/hash the selection, and evaluate only on an independent held-out sample. Keep the current output labeled as a frozen-sample software regression until that change and independent review are complete.

### P1 — CMS-like model coverage is still deliberately partial

- `src/heplab/physics/detector.py` and `kernels/physics-core/src/trajectory.rs` provide ideal-solenoid/analytic trajectories and guide-surface intersections, not full detector material navigation or measured hits.
- `kernels/physics-core/src/material.rs` models a declared thin homogeneous slab, continuous mean loss and the Gaussian core of Highland scattering. It omits energy-loss straggling, secondaries, showers and a volume navigator; results carry `educational_unvalidated` maturity.
- The current CMS field uses nominal 3.8 T checks and does not resolve run-era/IOV conditions for the analyzed sample. CMS itself describes a tracker and calorimeters inside the solenoid and muon chambers through the return yoke; that layered material and field structure matters for transport fidelity.
- `src/heplab/physics/cms_resonance_validation.py` documents approximate fit errors that omit background-fit uncertainty. Existing comparison bands and corrections/systematics also have acknowledged limits.

**Fix:** keep the educational/reference labels adjacent to controls and exports. Prioritize a run/IOV-resolved field and geometry/material map, then compare boundary crossings, momentum/energy ledgers and response against an independent CMSSW/Geant4 reference with frozen fixtures and held-out cases. Add straggling/secondary physics only with an accepted model and validation data. Include background and systematic covariance in mass-fit uncertainty before making measurement-level claims. The PDG reference gives the Bethe mean loss domain and corrections; it is not by itself proof that an end-to-end detector response is calibrated.

### P1 — New docs “Edit this page” links point to the wrong source tree

`web/HEPLab.Web/Pages/Docs.cshtml` generates GitHub links under `web/Content/Docs/...`, while the files live under `web/HEPLab.Web/Content/Docs/...`. Every rendered edit link for a docs page will point to a nonexistent path.

**Fix:** generate the source URL from the actual repository path, handle `.mdx` explicitly, and add a route/link contract check for every navigation item, source link and example asset before launch.

### P1 — Markdown/MDX conversion is fragile and emits raw HTML

`web/HEPLab.Web/Services/SiteContentService.cs` converts selected Astro/MDX components with regex replacements and then renders with Markdig AdvancedExtensions. `Docs.cshtml` emits the result through `Html.Raw`. This is manageable for a fixed, repository-controlled corpus, but content changes outside the small supported syntax can silently render incorrectly. If content ever becomes user-authored or remotely edited, raw HTML makes the trust boundary unsafe. Heading TOC IDs are also independently slugified and may drift from Markdig’s generated IDs.

**Fix:** migrate docs to ordinary Markdown plus explicit Razor components, or adopt a parser for the actual MDX subset. Disable raw HTML or sanitize it with a documented allowlist. Use one ID-generation path for headings and TOC anchors. Add content fixtures covering callouts, links, headings with punctuation, code fences and all embedded components. Before production, configure a CSP and appropriate security headers with an explicit allowance plan for the site’s scripts/styles.

### P2 — One duplicate IPC operation entry in the current diff

`src/heplab/desktop/worker.py` defines `"jobs.list"` twice in the operation mapping (around lines 274 and 277). Python silently keeps the later entry, so this is not currently a runtime failure, but it makes the patch harder to reason about and may hide a mistaken insertion.

**Fix:** remove the duplicate and keep the worker operation table as the single source of truth; verify its operation set against the shell protocol in the packaged worker acceptance path.

### P2 — GUI complexity and accessibility need user evidence

The workbench has solid capabilities: run lifecycle and committed results are visually modeled, selection links the event/table/inspector, controls show units, keyboard shortcuts exist, replay respects reduced motion, and WebGL has a Canvas2D fallback. The public site also labels teaching fixtures as synthetic and separates local simulation from public reading material.

The main workspace still combines data selection, analysis, detector display, simulation parameters, navigation, calibration and results. The engineering GUI review itself says representative-user and assistive-technology studies remain outstanding. The documented Canvas2D fallback also has lower detail (muon-only drawing), which should be communicated when that renderer is active.

**Fix:** run task-based studies around “load data → run → inspect event → understand validation state → export”; progressively disclose advanced physics settings; test minimum window sizes, keyboard-only and screen reader use, focus visibility, zoom/reflow, high contrast and reduced motion on packaged apps. Keep canvas information available in linked tables and expose reduced renderer capabilities in the UI. WCAG 2.2 is a useful baseline for keyboard and focus behavior; it does not replace native-app accessibility review.

### P2 — Project scale and language surface need stronger ownership boundaries

The monorepo combines Python analysis/API, Rust numerical core, C++ simulator runtime/container, Tauri/Rust desktop shell, a browser workbench, and a new .NET site. The architecture handbooks help explain the boundaries, but this many toolchains increases release, package, security-update and contributor costs. The web replacement also makes a previously static-oriented product depend on a server runtime.

**Fix:** keep each boundary only where it provides a measured advantage; define versioned contracts and owners for Python↔Rust, Tauri↔worker and website content/build. Publish a single release matrix showing supported platforms, runtime prerequisites, validation scope and artifact links. Pin direct actions and runtime dependencies, generate an SBOM/license inventory, and test clean-machine install/update/uninstall paths.

## Suggested order of work

1. Identify the actual production surface, host, URL, existing routes, and rollback owner. Do not deploy the current working tree until the Astro-to-Razor migration is intentional and host compatibility is confirmed.
2. Fix mass-dependent candidate selection and label the current regression’s validation scope honestly.
3. Fix the documentation source links, MDX conversion/HTML trust boundary, and navigation/anchor contracts.
4. Remove the duplicate IPC entry; run the CI-equivalent software and physics regression gates on the reviewed candidate.
5. Add and exercise production deployment or signed desktop release automation, followed by smoke checks and rollback verification.
6. Collect usability/accessibility evidence and expand transport physics only against independent references and held-out measurements.

## Advanced prompt to keep in the chat prompt library

Use this as the reusable project prompt. A product’s chat bar must separately support pinning it as a Tab-completable prompt suggestion; putting text in a repository file does not automatically register it in the chat UI.

```text
Act as the senior scientific-software engineer and release reviewer for HEPLab, a research/education project for reproducible LHC analysis and particle-detector simulation. Work from the current repository state, including uncommitted changes. Start by reading AGENTS.md and the engineering handbook, then map the source tree, Git status/branch/remotes, all build/test/release workflows, and any documented production host. Do not assume a deployment target or that a successful build means the physics is valid.

Goal: turn the requested change into a reviewable, reproducible release candidate for the explicitly identified production surface (public website, desktop package, or local Workbench). First state which surface and host/URL you found. If that cannot be established from the repository and connected deployment configuration, continue with analysis, fixes, and a local buildable candidate, but do not publish to a guessed target. Preserve existing user changes and data; never reset, clean, force-push, or overwrite them.

Review these layers separately:
1. Physics and calculations: units and dimensional consistency; coordinate/charge conventions; conservation and boundary behavior; numerical stability; model-domain limits; field/material/geometry conditions; statistical assumptions and uncertainty; random-seed reproducibility; independent references and held-out validation. Detect target leakage, selection sculpting, circular benchmarks, missing backgrounds/systematics, and claims stronger than the evidence.
2. Data and provenance: schema contracts, source ranges, event weights including negative weights and sumw2, certification, cache identity, hashes, environment/version capture, and export reproducibility.
3. Engine and architecture: Python/Rust/C++ parity, IPC/API validation and limits, cancellation, errors, concurrency, resource use, ownership of contracts, dependency boundaries, and clean installation/update/uninstall behavior.
4. Event display and GUI: distinguish truth, prediction, simulated hits and measured data; preserve linked selection and units; inspect renderer fallback parity; keyboard, focus, assistive technology, reduced motion, narrow windows, empty/error/loading states, and user task completion.
5. Website and security: route and asset completeness, accessibility, responsive behavior, source/edit links, content parsing/sanitization, CSP/security headers, privacy, runtime/host compatibility, SEO and honest capability claims.
6. Release: confirm exact commit/source state, reproducible build, CI status, artifact signing, deployment target, secrets/configuration, smoke checks, monitoring, rollback, and public release notes.

For every finding, cite exact file and line(s), explain user/scientific/release impact, assign severity (blocker/high/medium/low), distinguish confirmed defects from known model limitations and recommendations, and give a concrete fix plus an acceptance criterion. Prioritize correctness and scientific trust over optimization. Do not silently expand scope or change validated outputs. Make only changes necessary for the stated goal, keep changes small, and report every modified file.

Before any release action, show the exact candidate commit/version, destination, changes being published, validation evidence and rollback route. Publish only when the destination is explicitly configured and the task authorizes that release. Finish with: summary, findings and fixes, commands/results, remaining scientific limitations, production URL/artifact if verified, and next actions. Never describe software tests as physics validation.
```
