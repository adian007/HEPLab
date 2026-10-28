# 07 · Future improvements

Ordered by priority. Each item says what is wrong today, what to do, and how to
know it is done. Remove an item when it ships; do not mark it "done" and leave it.

## 1. Correctness and hygiene (do first)

### 1.1 Pin dependency versions
**Now:** `react`, `vite`, `typescript`, `lucide-react` and others are `latest` in
`package.json`. A fresh install can pull a breaking major version (this already
happened once: `lucide-react` 1.x removed the `Github` icon).
**Do:** pin exact versions from the lockfile; update on purpose with a changelog read.
**Done when:** no `latest` in `package.json` and CI installs with `--frozen-lockfile`.

### 1.2 One source for capabilities
**Now:** capability names and maturity exist twice: in `src/content.ts` and in
`overview()` in `src/heplab/server/project.py`. The site uses only `content.ts`,
so the two can drift.
**Do:** pick one. Recommended: the API owns `id`, `name` and `status`; `content.ts`
keeps the longer descriptions keyed by `id`.
**Done when:** changing a capability's status in one place changes the page.

### 1.3 Automated tests
**Now:** only `tsc` runs. All behaviour checks in
[06-build-and-review-rules.md](06-build-and-review-rules.md) are manual.
**Do:**
- Vitest unit tests for `src/components/trackPhysics.ts`, using the reference
  values in [04-event-display.md](04-event-display.md), and for `useRemote`
  (ready, offline, abort on unmount).
- One Playwright smoke test: loads with API up and down, no console errors, no
  horizontal scroll at 375 px, theme persists across reload.
- Run both in the existing GitHub Actions workflow.
**Done when:** a pull request that breaks any of these fails CI.

### 1.4 Lint and format
**Now:** no ESLint or formatter. Some lines in `App.tsx` and `TrackLab.tsx` are
long one-liners that are hard to review.
**Do:** ESLint with `eslint-plugin-react-hooks`, and Prettier (or Biome) with a
line width of 120. Format once in a separate commit.

### 1.5 Do not publish source maps
**Now:** `vite.config.ts` sets `sourcemap: true`, and FastAPI serves the 2.3 MB
`.map` file from `/assets`.
**Do:** use `sourcemap: 'hidden'` and keep maps as a CI artifact.

### 1.6 Move the inline theme script
**Now:** `index.html` contains an inline `<script>` that applies the saved theme.
A strict content security policy (the desktop shell has one) blocks it; the page
still works but may flash the wrong theme and logs a CSP error.
**Do:** move it to `public/theme.js` and load it with a normal `<script src>`
in `<head>`.

### 1.7 Repository link
**Now:** `brand.repository` and `project.py` point to
`adian007/QuantumArtGenerator-Cybersecurity`, which does not match the project name.
**Do:** move the code to a repository named for HEPLab, then update both places.

## 2. Performance

### 2.1 Load the chart library only when needed
**Now:** 500 kB of JavaScript (166 kB gzip), mostly Observable Plot, loads before
first paint even though the chart is halfway down the page.
**Do:** `React.lazy` the `EvidenceFigure` component and render it when the
section approaches the viewport.
**Done when:** initial JavaScript is under 200 kB and Vite's chunk-size warning is gone.

### 2.2 Ship only the font subsets used
**Now:** 15 font files are built, including Cyrillic, Greek and Vietnamese.
Browsers only download what they need, but the build and cache are larger than
necessary.
**Do:** import the Latin `wght` subset CSS for each family.

## 3. Content the product plan asks for

[`docs/web/01-product-and-information-architecture.md`](../../docs/web/01-product-and-information-architecture.md)
lists sections this site does not have yet:

- **Simulator**: platform-specific install and run steps from
  `docs/engineering/sim-runtime.md`, with the reference bench and native runtime
  compared side by side.
- **Learn**: a guided path from event record to detector response to
  reconstructed objects, using real, sourced examples.
- **Community**: contribution guide, good first issues, code review path,
  security reporting, citation (`CITATION.cff`).
- **Releases**: only once an installer exists. Show actual assets and the
  supported platform matrix.

When the page gets long enough that these do not fit, split into routes
(`/`, `/simulator`, `/learn`, `/docs`, `/community`) and add a router. Not before.

Smaller content work:

- Real screenshots of the `/workbench` UI, labelled with the version they show.
- An Open Graph image so shared links have a preview.
- Update `desktop_status` in `project.py` when the Windows build is distributed.

## 4. Event display

- Load a real run artifact exported by the simulator and draw it in the same
  view, clearly labelled with its run ID, seed and engine, next to the
  illustrative mode.
- Add an XZ (side) view toggle.
- Add a momentum-resolution readout with its formula and assumptions stated,
  and a unit test for it.
- Provide a text alternative: a small table of the highlighted track's values
  for screen-reader users.

## 5. Hosting

The site is only served by the local FastAPI app today. To host it publicly
(for example GitHub Pages):

- Add a Vite `base` setting for the hosting path.
- At build time, snapshot the evidence JSON with its source hash into the
  bundle, show the snapshot date, and fall back to it when no API is present.
- Keep the rule that a hosted site never offers to run simulations.
- If analytics are ever added: privacy-respecting, no cookies, documented on the
  page.
