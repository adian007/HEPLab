# HEPLab project website

Design and engineering notes for this site are in [`docs/`](docs/README.md).

This is the public project overview site. It explains the simulator project,
implemented capabilities, evidence, technical architecture, roadmap, and how to
get involved. **It does not run simulations.** The simulator remains a local
application and is intended to become a desktop app.

## Stack

- React + TypeScript + Vite frontend.
- Single-page site: hero, interactive sagitta demo (`components/TrackLab.tsx`,
  analytic helices computed in the browser), capabilities with a maturity scale,
  live evidence, architecture, quickstart, searchable docs, limits and roadmap.
- Content in `src/content.ts`; read-only API hook in `src/lib/api.ts`.
- Design tokens and light/dark themes in `src/styles/site.css`.
- Observable Plot for responsive, source-linked scientific evidence figures.
- Locally bundled Space Grotesk (display), Inter (text) and JetBrains Mono (data).
- Python 3.12 / FastAPI read-only project-overview endpoint.
- Existing FastAPI app serves the production frontend from `web/dist`.
- No account system, hosted compute, data uploads, or simulator control API is
  exposed by this site.

## Develop

```powershell
pnpm --dir web install
$env:PYTHONPATH = "src"
python -m heplab.cli gui --port 8765
```

In another terminal:

```powershell
pnpm --dir web dev
pnpm --dir web typecheck
pnpm --dir web build
```

Vite serves the site at `http://127.0.0.1:5173` and proxies the public summary
request to FastAPI. The dev server does not send run requests. The production
overview is served at the Python app root after build. The local simulator
workbench remains available at `/workbench`; `heplab gui --open-browser` opens
that route directly.

See [site and desktop architecture](../docs/web/README.md).
