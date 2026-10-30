# Website backend boundary

## Static project guide

The Astro/Starlight guide is static documentation. It does not call FastAPI,
submit jobs, read local events, or inspect artifacts. Build it with
`pnpm --dir web build` and host the generated `web/dist/` directory. Visitors
must run the simulator locally to access the workbench.

## Simulator service

The separate local simulator stack uses Python, FastAPI, Pydantic, and HEPLab
application services. It serves the workbench and local APIs for capabilities,
datasets, jobs, runs, and event inspection. Rust kernels and the registered
PYTHIA8/DELPHES runtime are separate execution capabilities.

The API is a local application boundary, not an API consumed by the public
project guide. Contracts and security controls are documented in
`docs/engineering/12-interfaces.md` and related handbook pages.

## Topology

```text
Static host: Astro/Starlight pages ── documentation only

Local machine: workbench UI ── FastAPI adapter ── Python services ── engines
```

Keep simulation execution, artifact access, and filesystem authority in the
local application. Public documentation can link to source records without
having access to a visitor's machine.
