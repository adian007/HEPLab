# Build and review

## Edit pages

1. Put public guide content in `HEPLab.Web/Content/Docs/`.
2. Keep technical contracts and detailed scientific methods in the engineering
   handbook, then link to the canonical record.
3. Check each capability and status against the current implementation.
4. Add curated sidebar entries in `HEPLab.Web/Services/SiteContentService.cs` when needed.

## Commands

```powershell
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

The build compiles the Razor Pages app. For browser review, run
`dotnet run --project web/HEPLab.Web` and open the printed URL. The guide does
not need FastAPI running.

Run `tools/check_site_runtime.py` against both the built DLL (with the project
directory as `--content-root`) and published DLL, as shown in
[`web/README.md`](../README.md). It starts each app in Production and checks real
asset bodies, MIME types, compression, and search. An HTTP 200 response with an
empty CSS or JavaScript body is a failure. Also inspect the rendered page at
desktop and mobile widths; a text or accessibility snapshot cannot confirm CSS.

## Review points

- Every technical claim has a current repository source.
- Software execution is not described as physics validation.
- Every figure has units, provenance, and a clear statement of scope.
- Links work as static routes and external links point to verified project
  documents.
- Pages remain readable at narrow widths and in both themes.
- The guide makes clear that simulation runs locally in the Python workbench.
