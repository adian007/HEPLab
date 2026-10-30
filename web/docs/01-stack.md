# Stack and commands

## Runtime

| Layer | Choice | Purpose |
|---|---|---|
| Web framework | ASP.NET Core Razor Pages on .NET 10 | Server-rendered guide pages, route handling, and hosting. |
| Markdown | Markdig | Render authored Markdown/MDX guide content into HTML. |
| UI library | Bootstrap 5.3.8, locally vendored | Responsive grid, buttons, forms, progress, and focus-managed mobile offcanvas navigation. |
| Components | C# Tag Helpers and Razor partials | Shared icons, navigation, fixture preview, lab, gallery, and page layout. |
| Typography | Local IBM Plex Sans/Mono 1.1.0 packages | Body/interface typography and technical labels; SIL OFL licenses included. |
| Browser behavior | Bootstrap bundle and focused JavaScript | Keyboard search, theme selection, clipboard actions, lab checkpoints, and gallery filters. |
| Static assets | ASP.NET Core static web assets | Serve the logo, CSS, scripts, and self-contained HTML examples. |

The web app does not call the local FastAPI service or run simulations. The
Python workbench remains a separate local application.

## Commands

Run from the repository root:

```powershell
dotnet run --project web/HEPLab.Web
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

`dotnet run` prints the local URL. Publishing creates an ASP.NET Core app for a
.NET 10 host; the site is not a static directory anymore.

## Source layout

- `HEPLab.Web/Program.cs`: service registration, static assets, pages, and search endpoint.
- `HEPLab.Web/Pages/`: home, documentation route, and shared Razor layout.
- `HEPLab.Web/Services/SiteContentService.cs`: content loading, Markdown rendering, curated navigation, and search data.
- `HEPLab.Web/Services/ExperimentPreviewService.cs`: reads the fixed fixture's declared settings and result provenance.
- `HEPLab.Web/wwwroot/js/detector-view.js`: renders fixture coordinates and declared cylindrical/disk surfaces as an interactive 3D perspective scene; it runs no simulation.
- `HEPLab.Web/Content/Docs/`: page source with YAML front matter.
- `HEPLab.Web/wwwroot/`: branding, styles, JavaScript, and offline examples.
- `docs/`: maintainer notes for design, writing, and review.
