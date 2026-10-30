# Site architecture

## Request flow

ASP.NET Core Razor Pages serves the public guide. A singleton content service
loads authored Markdown from `HEPLab.Web/Content/Docs`, reads page metadata,
renders Markdown with Markdig, and exposes the same page set to the search
endpoint. Razor Pages provides the shared header, navigation, table of contents,
and route handling.

The interface is composed from `Pages/Shared/` Razor partials and a C#
`LabIconTagHelper`. Bootstrap 5.3.8 supplies the grid, controls, and mobile drawer.
The lab and gallery are allowlisted Razor embeds, rather than HTML strings inside
the Markdown service. Authored raw HTML stays disabled. `ExperimentPreviewService`
reads the versioned synthetic fixture's settings, geometry identity, event index,
and result digest. The home-page Canvas 2D renderer fetches that same fixture and
projects its stored 3D trajectories and surface coordinates interactively; it
runs no simulation. Solid path segments lie inside the ideal uniform-field bore;
dashed segments lie outside it, where this model sets the field to zero.

```text
Markdown pages ── SiteContentService / Markdig ── Razor Pages ── ASP.NET Core host
                                                      │
                                                      ├── search-index.json
                                                      └── static JS and media
```

The home page is `HEPLab.Web/Pages/Index.cshtml`. The curated sidebar lives in
`SiteContentService.cs`. Search is a small browser client over
`/search-index.json`, so it works in local development and in a published app.

## Editing content

- Add or update a Markdown page under `HEPLab.Web/Content/Docs/`.
- Set a concise `title` and `description` in its front matter.
- Add the route to `SiteContentService.cs` when it belongs in the curated sidebar.
- Link related pages with site routes, for example `/simulation/models/`.
- Keep project status tied to the repository and engineering handbook; distinguish software execution evidence from physics validation.

The education lab and results gallery are small browser interactions implemented
in `wwwroot/js/`. Keep their sample data and claims aligned with the source JSON
and engineering records.

## Runtime boundaries

The web app renders documentation and serves the fixed browser teaching sample.
It does not call the local simulator API, accept uploads, or read a visitor's
result files. The local Python workbench owns simulation controls and execution.
The app requires an ASP.NET Core 10 host, while offline exported examples remain
standalone HTML files.

All interface assets are served locally. Bootstrap, fonts, licenses, and SHA-256
records are under `wwwroot/vendor`. Razor asset helpers use the .NET fingerprint
manifest; styles and scripts receive new URLs when their bytes change. Production
runtime checks cover built and published hosts, every indexed guide page, local
links and anchors, fonts, asset bytes, exact fixture delivery, and the field and
curvature conventions used by the home 3D perspective view.
