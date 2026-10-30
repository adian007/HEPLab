# Site architecture

## Page flow

Astro and Starlight render the public guide as static HTML. The docs collection
is sourced from `src/content/docs/`; filenames become routes. Starlight builds
the navigation, breadcrumbs, table of contents, edit links, and Pagefind search
index from this content.

```text
Markdown / MDX ── Astro content collection ── Starlight ── static dist/
                                                              │
                                                              └── static host
```

The homepage is `src/content/docs/index.mdx`. It uses Starlight's splash
template, short project summary, and links to the most useful guides. Sidebar
groups and repository links are configured in `astro.config.mjs`.

## Editing content

- Add or update a Markdown page under `src/content/docs/`.
- Set a concise `title` and `description` in its frontmatter.
- Add the route to `astro.config.mjs` when it belongs in the curated sidebar.
- Link related pages with their site routes, for example `/simulation/models/`.
- Keep project status tied to the repository and engineering handbook; distinguish
  software execution evidence from physics validation.

Starlight components such as `Aside`, `CardGrid`, and `LinkCard` are available
for cases where they improve navigation or explain a concrete relationship.
Prefer ordinary headings, lists, tables, and links for the rest.

## Runtime boundaries

The public guide contains no API calls and does not load run artifacts. Static
hosting cannot start the local simulator or read a visitor's files. The local
Python workbench owns simulation controls and execution. Its API and UI remain
documented in the engineering handbook.

The generated site needs JavaScript for interactive Starlight controls such as
search and mobile navigation; reading the documentation does not depend on a
custom application bundle or a running backend.
