# HEPLab project guide

This directory contains the static documentation website built with Astro and
Starlight. It explains the local simulator, analysis workflow, evidence,
limitations, and contribution path. It does not execute simulations or connect
to a local API.

## Develop

```powershell
pnpm --dir web install
pnpm --dir web dev
```

Open the local URL printed by Astro. Pages are written in Markdown and MDX under
`src/content/docs/`; navigation, project identity, and Starlight configuration
live in `astro.config.mjs`. Site-specific CSS is in `src/styles/site.css`.

## Check and build

```powershell
pnpm --dir web check
pnpm --dir web build
pnpm --dir web preview
```

The static output is written to `dist/`. Starlight provides the documentation
layout, responsive navigation, theme switcher, and search index. Deploy the
contents of `dist/` to a static host. The Python workbench remains a separate
local application, started with `heplab gui` or `tools/start_workbench.ps1`.

See [website and desktop architecture](../docs/web/README.md) and the
[site maintainer notes](docs/README.md).
