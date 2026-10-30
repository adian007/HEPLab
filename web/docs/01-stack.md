# Stack and commands

## Runtime

| Layer | Choice | Purpose |
|---|---|---|
| Site framework | Astro | Builds static pages for direct hosting. |
| Documentation | Astro Starlight | Markdown and MDX pages, navigation, search, responsive layout, and theme controls. |
| Type checking | TypeScript and `@astrojs/check` | Checks Astro configuration and content integration. |
| Package manager | pnpm | Exact dependency versions and lockfile in `pnpm-lock.yaml`. |

The site has no React application, client API adapter, simulator controls,
tracking, analytics, or required runtime JavaScript. Starlight provides its
search index during a static build. The local simulator remains a separate
Python application.

## Commands

Run from the repository root:

```powershell
pnpm --dir web install
pnpm --dir web dev
pnpm --dir web check
pnpm --dir web build
pnpm --dir web preview
```

Astro prints the development URL. The build writes static files to `web/dist/`;
deploy that directory to a static host. The website does not depend on the
FastAPI service. Start the local simulator separately with `heplab gui` or
`tools/start_workbench.ps1`.

## Source layout

- `astro.config.mjs`: Starlight identity, navigation, edit links and CSS.
- `src/content/docs/`: site pages and guides, organized by section.
- `src/content.config.ts`: Starlight's documentation collection.
- `src/styles/site.css`: small set of site-level Starlight theme adjustments.
- `public/`: logo and favicon copied to the static output.
- `dist/`: generated site; do not edit by hand.
