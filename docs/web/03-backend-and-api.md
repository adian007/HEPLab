# Website backend boundary

## Public guide

The public guide runs as an ASP.NET Core app. It renders documentation and
serves its search index and static examples. It does not call FastAPI, submit
simulation jobs, inspect a visitor's files, or expose the local simulator API.
Run the app with `dotnet run --project web/HEPLab.Web`; publish it to an
ASP.NET Core 10 host.

## Local simulator service

The separate local simulator stack uses Python, FastAPI, Pydantic, and HEPLab
application services. It serves the workbench and local APIs for capabilities,
datasets, jobs, runs, and event inspection. Rust kernels and the registered
PYTHIA8/DELPHES runtime are separate execution capabilities.

The API is a local application boundary, not an API consumed by the public
project guide. Contracts and security controls are documented in
`docs/engineering/12-interfaces.md` and related handbook pages.

## Topology

```text
Public host: ASP.NET Core guide ── documentation and search

Local machine: workbench UI ── FastAPI adapter ── Python services ── engines
```

Keep simulation execution, artifact access, and filesystem authority in the
local application. Public documentation can link to source records without
having access to a visitor's machine.
