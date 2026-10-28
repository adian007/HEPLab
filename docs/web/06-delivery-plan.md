# Website and desktop delivery plan

This plan separates product discovery from scientific and packaging claims.
Milestones close only with recorded implementation evidence.

## Milestones

### W0 — foundation (current)

- Establish `web/` and enhanced product/technical documents.
- Confirm current simulator UI, backend routes, runtime support and limitations.
- Keep the existing Python-served UI as the working application.

### W1 — open-source project site (implemented)

- React/TypeScript overview, project summary endpoint, capabilities, evidence,
  architecture, roadmap, searchable docs index, FAQ, and contribution links.
- The site clearly states that the simulator is local and the desktop app is
  planned, not currently distributed.

### W2 — public project API

- Initialize the React/TypeScript package, strict type checks and locked build.
- Version and expand the read-only overview schema only when project status
  content needs structured updates; keep repository documents authoritative.

### W3 — public launch and content maintenance

- Choose public hosting, connect actual release/issue links, and keep the status
  endpoint and project docs synchronized with implementation evidence.
- Preserve the strict boundary: no hosted simulator or browser run controls.

### W4 — desktop application

- Select and implement a shell after measuring Python/runtime packaging options.
- Add supervised service lifecycle, installers, platform support matrix, signing,
  notices, update/rollback and data migration.
- Publish only after clean-machine and native-runtime evidence.

## Decisions to resolve before implementation

1. Is the website a public GitHub Pages/static site, or is there another host?
2. Should the first public release be a project landing site, interactive local
   simulator, or both? Recommended sequence: landing site, then client migration.
3. Which desktop platform is the first supported install target? Existing native
   simulation guidance is Windows via WSL Ubuntu and Linux x86-64; the portable
   reference bench has broader potential support.
4. What repository URL, issue tracker, screenshots and project identity assets
   should the site publish? Use current repository metadata; do not invent links.

## Acceptance checklist

- A new visitor can explain what HEPLab does, what is implemented, and what is
  not physics-validated.
- A contributor can find setup, architecture, contribution and license guidance.
- A local user can discover capabilities, run/cancel a bounded job and inspect
  a result without granting the UI arbitrary filesystem authority.
- Browser and future desktop packaging use the same API and presentation code.
- Scientific output preserves run identity, immutable artifacts, provenance,
  units and validation state.
- Build assets are reproducible, offline-capable and reviewed for licenses and
  unwanted network calls.
