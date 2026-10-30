# Archived React + Vite project site

This is the preserved React + TypeScript + Vite version of the public project
site. It is kept so its source and content are not lost while the current guide
lives in `web/HEPLab.Web`. It is not the physics workbench and is not used by the
current build or release workflows.

To run this archived version from the repository root:

```powershell
pnpm --dir legacy/web-vite install
pnpm --dir legacy/web-vite dev
```

Its original read-only API proxy targets the local Python service at
`http://127.0.0.1:8765` unless `HEPLAB_API_TARGET` is set.
