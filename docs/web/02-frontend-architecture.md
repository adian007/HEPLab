# Frontend architecture

## Selected direction

Astro and Astro Starlight build the public project guide as a static site.
Project pages are Markdown or MDX in `web/src/content/docs/`. Starlight supplies
the documentation layout, sidebar, responsive navigation, theme switcher,
breadcrumbs, table of contents, edit links, and search.

The site describes the simulator; it does not execute it. It has no API
integration and does not access local runs. The Python workbench remains a
separate local application.

## Workspace layout

```text
web/
├── astro.config.mjs            Starlight identity, navigation, links, styles
├── package.json                Astro/Starlight scripts and pinned dependencies
├── pnpm-lock.yaml              reproducible package resolution
├── public/                     logo and favicon
└── src/
    ├── content.config.ts       Starlight documentation collection
    ├── content/docs/           Markdown and MDX pages
    ├── assets/                 bundled source assets
    └── styles/site.css         small theme customizations
```

## Content workflow

Add a Markdown page under `src/content/docs/` with `title` and `description`
frontmatter. Add its slug to the sidebar in `astro.config.mjs` if it should be
visible in curated navigation. Use regular Markdown for most content and
Starlight components when they help readers find a page or understand a caveat.

Detailed scientific algorithms and validation records belong in
`docs/engineering/`. The site summarizes them and links to the canonical source.

## Rendering and design

Astro produces static HTML and Starlight builds the search index from the pages.
Keep the content semantic and readable without custom client-side behavior.
Starlight's built-in search and navigation provide the small interactive layer.
Use its theme variables for custom colors; preserve keyboard access, visible
focus, responsive reflow, and reduced-motion behavior.

## Build

```powershell
pnpm --dir web check
pnpm --dir web build
```

The build writes `web/dist/`, which can be hosted by a static file service. The
site does not require the FastAPI service. Start the local workbench separately
when documenting or reviewing simulator behavior.
