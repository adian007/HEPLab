# 01 · Stack

## Runtime and tools

| Layer | Choice | Version installed (Oct 2026) | Why |
|---|---|---|---|
| UI library | React | 19.3 | Component model the team already uses; no SSR needed. |
| Language | TypeScript, `strict` | 7.0 | Catches payload-shape and null errors at build time. |
| Bundler / dev server | Vite with `@vitejs/plugin-react` | 8.3 / 6.1 | Fast dev server, `/api` proxy, static output FastAPI can serve. |
| Charts | Observable Plot | 0.6.17 | Small API for scientific scatter plots with log axes. |
| Icons | lucide-react | 1.61 | Consistent stroke icons, tree-shaken per import. |
| Fonts | Fontsource variable: Space Grotesk, Inter, JetBrains Mono | 5.3 | Self-hosted, no third-party font requests. |
| Package manager | pnpm | 12 | Lockfile at `web/pnpm-lock.yaml`. |
| Backend (not in `web/`) | FastAPI, Python 3.12 | — | Serves the built site and the read-only project endpoints. |

There is no CSS framework, router, state library or component library. The page
is small enough that they would add more code than they remove.

`package.json` currently pins most packages to `latest`. That is a known problem;
see [07-future-improvements.md](07-future-improvements.md).

## Commands

Run from the repository root.

```bash
pnpm --dir web install
pnpm --dir web dev          # http://127.0.0.1:5173, proxies /api to :8765
pnpm --dir web typecheck
pnpm --dir web build        # writes web/dist
```

The API the site reads comes from the local HEPLab service:

```bash
heplab gui --port 8765
```

Set `HEPLAB_API_TARGET` to point the dev proxy at another address.

## How the built site is served

`pnpm build` writes `web/dist/index.html` and hashed files in `web/dist/assets/`.
`src/heplab/server/app.py` serves them:

| Route | Response |
|---|---|
| `/` | `web/dist/index.html` if it exists, otherwise the bundled workbench page. `no-store`. |
| `/assets/*` | Files from `web/dist/assets`, cached for a year as immutable (names are content-hashed). |
| `/workbench` | The local simulator UI. Not part of this site. |
| `/api/v1/project/overview` | Read-only project summary, `max-age=60`. |
| `/api/v1/project/evidence` | Read-only validation excerpt, `max-age=300`. |

Both project payloads are built in `src/heplab/server/project.py`. Edit wording
there, not in `app.py`. A test checks that the web endpoint and the desktop
worker return the same JSON.

## Desktop shell

Inside the Tauri desktop app, a content security policy blocks `fetch('/api/...')`.
`src/lib/desktop.ts` detects the shell (`window.__TAURI_INTERNALS__`) and sends
the same requests through the shell's `heplab_invoke` command instead. In a
browser this path is never taken. Only URLs listed in its `OPERATIONS` table
work on desktop; anything else falls back to the offline state.

## Current build size

From `pnpm build` on 28 Oct 2026:

| File | Size | Gzip |
|---|---|---|
| JavaScript | 500 kB | 166 kB |
| CSS | 28 kB | 8 kB |
| Source map | 2.3 MB | served publicly today |
| Fonts | 15 `.woff2` files | browsers fetch only the subsets a page uses |

Most of the JavaScript is Observable Plot and its d3 dependencies.
