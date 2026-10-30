# Build and review

## Edit pages

1. Put public guide content in `src/content/docs/`.
2. Keep technical contracts and detailed scientific methods in the engineering
   handbook, then link to the canonical record.
3. Check each capability and status against the current implementation.
4. Add sidebar entries in `astro.config.mjs` when needed.

## Commands

```powershell
pnpm --dir web check
pnpm --dir web build
```

The build runs Astro's content/type checks and writes the static output to
`web/dist/`. For visual review, run `pnpm --dir web dev` and open the URL Astro
prints. The static site does not need FastAPI running.

## Review points

- Every technical claim has a current repository source.
- Software execution is not described as physics validation.
- Every figure has units, provenance, and a clear statement of scope.
- Links work as static routes and external links point to verified project
  documents.
- Pages remain readable at narrow widths and in both Starlight themes.
- The guide makes clear that simulation runs locally in the Python workbench.
