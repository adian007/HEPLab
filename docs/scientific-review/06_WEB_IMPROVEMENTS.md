# 06 — Website and Scientific Documentation Improvements

## Current web surfaces

The active website source in the checkout is a separate ASP.NET Core 10 Razor Pages
application. `SiteContentService` reads Markdown/MDX files under
`web/HEPLab.Web/Content/Docs`, renders them with Markdig, constructs navigation and a
search index, and adds fixed interactive demonstrations for a synthetic Z analysis
and a static example gallery. Its documentation covers capabilities, limitations,
simulation tiers, validation evidence, reading result provenance, architecture and
installation. The pages repeatedly label examples as synthetic and distinguish
software/reference checks from detector calibration. Those choices support
scientific credibility.

The source contains one skip link, semantic navigation, selectable theme, keyboard
search dialog, headings and responsive styles. That is evidence of intentional
accessibility work, not a completed WCAG audit. `/site` is an ignored generated
artifact, not a second active website source. The canonical application is
`web/HEPLab.Web`; production hosting and deployment are still not verified.

## Implementation status after review

The ASP.NET/Razor architecture is confirmed as the active source by the project
README. Documentation edit links now resolve under its actual content directory;
the source mapper covers Markdown and the three supported MDX pages. Markdig disables
authored raw HTML, while the two built-in interactive embeds render through
allowlisted Razor partials. The table of contents uses the heading IDs emitted by the
renderer. `tools/check_site_contract.py` verifies routes, local links, source paths,
example downloads and generated evidence pages.

The local Production preview exposed a missing build asset manifest: HTML loaded
while CSS and JavaScript returned empty HTTP 200 responses. `Program.cs` now loads
static web assets explicitly for built-DLL previews. The Production runtime check
in [`tools/check_site_runtime.py`](../../tools/check_site_runtime.py) passes for
both Release build and publish output, covering all 19 indexed pages, 17 assets with
exact source bytes and MIME types under identity/gzip requests, and search JSON.
CI runs both checks. This verifies local delivery, not public deployment or a WCAG
audit; rendered browser review is also required. Local links, anchors, duplicate
IDs, page headings, font delivery, vendor hashes, fixture provenance, and the
Lorentz curvature convention are checked.

The site now uses locally vendored Bootstrap 5.3.8, IBM Plex typography, shared C#
Tag Helpers and Razor components, and a redesigned home/guide/lab/gallery interface.
The home 3D perspective view renders the existing synthetic fixture's stored 3D
coordinates and declared surfaces. It identifies μ−/μ+, q, axes in metres, the
uniform +z field, the 3 m zero-field boundary, the 1 mm silicon material sample,
the event index, geometry identifier, and actual result digest. Solid and dashed
segments distinguish the field and zero-field regions. Dark/light themes, keyboard search, copy
controls, responsive tables, and Bootstrap mobile navigation have local browser
coverage. Gallery thumbnails remain labeled schematic, and evidence categories
and the failed CMS gate remain explicit.

The education page now gives a first Workbench experiment with the uniform-field
radius, known scope, and a downloadable grouped config and synthetic result artifact.
The site also serves a versioned curvature/sagitta sweep with computed source hashes,
32 exact uniform-field cases and eight bounded OAE comparisons; the latter have no
field-measurement acceptance gate. The examples generator rebuilds the report and
static page from repository source. The gallery contains synthetic, PDG-table and
recorded-CMS examples generated from the checked-in fixtures. The CMS page shows its
failed held-out Υ(2S) gate and states that its same-file split is not an independent
dataset. The exporter distinguishes full-run and selected-event scope and preserves
source/model digests and privacy defaults.

Current deploy target, public hosting, and human accessibility/usability findings
remain unresolved; do not infer those from a successful local build.

## Original audit findings and implementation disposition

| Priority | Finding | Consequence | Recommended action |
|---|---|---|---|
| **P1 — done** | “Edit this page” URLs originally used the wrong path. | The path was invalid. | Links now resolve under `web/HEPLab.Web/Content/Docs`; site contract checks validate them. |
| **P1 — done, bounded MDX** | The Markdown/MDX renderer originally trusted raw HTML and maintained heading slugs separately. | Could misrender content or create an HTML injection boundary. | Raw HTML is disabled; only built-in tokens render trusted embeds; TOC IDs derive from rendered headings. Unsupported MDX remains unsupported. |
| **P1 — done for current pages** | Technical pages need a clear distinction among software parity, named-reference agreement, calibration, and physics validation. | Visitors could infer that matching a CMS software reference or using a CMS card means the workbench is calibrated. | Evidence pages and model/example content now describe the category and exact scope; no category is used as a synonym for another. |
| **P2 — done** | Readers lacked a guided first physics experiment. | The lesson was mostly the synthetic Z analysis. | The education page now includes the analytic bending equation, model limits, setup and result downloads. |
| **P2 — done** | The static Z lab and local Workbench could be confused as one runtime. | Readers could infer remote simulation. | The site calls its examples synthetic/static and ships a versioned Workbench setup and artifact without running simulations. |
| **P2 — source resolved; deploy open** | `/site` and ASP.NET appeared to be competing sources. | Could leave edit/deploy ownership unclear. | ASP.NET is canonical and contract-checked. `/site` is generated/ignored; production deployment still needs an owner and environment evidence. |

Source references: [site content service](../../web/HEPLab.Web/Services/SiteContentService.cs#L12),
[Razor documentation page](../../web/HEPLab.Web/Pages/Docs.cshtml#L1),
[site layout](../../web/HEPLab.Web/Pages/Shared/_Layout.cshtml) and
[project content](../../web/HEPLab.Web/Content/Docs/validation/evidence.md).

## Recommended information architecture

1. **Project and scientific motivation:** what HEPLab is, intended users and what
   “Muon Particle Simulator” means in this repository.
2. **First experiment:** one reproducible declared muon pair in a uniform field,
   with $R=p_T/(0.2998B)$ and an analytic expected result.
3. **How the Workbench works:** data source, model, run lifecycle, event display and
   export, with truth/prediction/measurement vocabulary.
4. **Physical models:** four-vectors, relativity, the separate fixed-momentum
   survival experiment, field, material and response equations; each page states
   units, assumptions, domains and omitted effects.
5. **Numerical methods:** analytic helix, RK4 field path, intersections, RNG,
   histogram uncertainty and precision/convergence results.
6. **Validation evidence:** a searchable table containing model ID, reference,
   sample, split, acceptance criterion, result, software version and what it does not
   establish.
7. **Installation and user guide:** supported platform/runtime matrix, clean install,
   first run, data import, error recovery and offline use.
8. **Known limitations and issues:** concise user-facing summary, linked to details.
9. **Roadmap and contribution:** measurable acceptance criteria and expected review.
10. **References, data citation, acknowledgments and reproducibility:** DOI, license,
    provenance and versioned examples.

## Shareable reproducible results

The Python HTML exporter already writes a self-contained offline page with interactive
histogram or event display, result digest, data kind, HEPLab version and export time.
The project guide has a static gallery for synthetic examples and states that local
runs are not uploaded. This is a good low-cost direction for a minimal-budget
project.

Extend its result manifest with:

```json
{
  "schema": "heplab-share-v2",
  "run_id": "...",
  "result_sha256": "...",
  "source": {"kind": "synthetic|cms-data|mc", "record": "...", "file_hashes": []},
  "configuration": {"model_id": "...", "seed": 42, "units": {}, "settings": {}},
  "software": {"heplab": "...", "python": "...", "rust_core": "...", "generator": "...", "delphes_card_sha256": "..."},
  "evidence": {"status": "...", "scope": "...", "references": []},
  "privacy": {"contains_local_paths": false, "raw_events_included": false}
}
```

Add optional interactive plot/event display, full configuration, RNG version, field
and geometry IDs, selected event index, parent run digest and provenance. Never include
raw CMS event rows or local filesystem paths by default. Keep `synthetic`,
`simulation`, `recorded data` and `illustration` visible in the exported page header
and figure captions. A public static gallery of a small curated set of reviewable,
synthetic experiments is feasible; a hosted upload service is unnecessary.

## Documentation presentation rules

- Every equation defines symbols and units; equations shown in the UI use the same
  model ID and parameter values as code.
- Every chart caption says source/sample, units, selection, sample size, statistical
  uncertainty and known systematic omissions.
- Present observed and expected values side-by-side; use consistent binning and state
  whether uncertainty is statistical only.
- Link benchmark reports to frozen fixtures and one-command reproduction steps.
- Do not use CMS logos or realistic detector imagery to imply full CMS transport.
- State “not calibrated” at the result, not only in an FAQ or legal page.
- Keep source-edit links, in-page anchors, navigation routes and examples under an
  automated content contract check.

