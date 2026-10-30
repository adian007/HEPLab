# HEPLab web application

The project guide is an ASP.NET Core Razor Pages application targeting .NET 10.
Markdown pages live in `HEPLab.Web/Content/Docs`; `Markdig` renders them on the
server. The app owns the shared layout, navigation, table of contents, themes,
search index endpoint, guided lab, and result gallery. Static assets and the
offline examples are under `HEPLab.Web/wwwroot`.

The shared UI uses Bootstrap 5.3.8, locally hosted IBM Plex Sans/Mono fonts, C#
Tag Helpers, and reusable Razor partials. The home event preview renders the
versioned synthetic muon fixture in an interactive perspective view. It shows
fixture 3D coordinates, declared detector surfaces, the +z field direction,
and the zero-field continuation outside the ideal 3 m bore. It runs no new
simulation and does not imply measured CMS data.
The lab and gallery are Razor components embedded in the authored guide. Asset
versions, licenses, and file hashes are recorded under `wwwroot/vendor/`.

## Run locally

Install the .NET 10 SDK, then from the repository root:

```powershell
dotnet run --project web/HEPLab.Web
```

Open the local URL printed by `dotnet run`. The web guide is independent of the
Python workbench and does not run simulations or read local result artifacts.

The app also loads the build asset manifest when a built DLL is launched in
Production mode. This keeps CSS, JavaScript, and their compressed responses
available during a local Release preview. A successful HTML response alone does
not verify the preview: check the rendered layout and asset response bodies.

## Build and publish

```powershell
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

The publish output is an ASP.NET Core app and must run on an ASP.NET Core 10
host. This is no longer a static-only site.

CI runs `tools/check_site_runtime.py` against both the Release build and publish
output in Production. The check requests all 19 indexed pages, checks internal
links and anchors, verifies unique IDs and one page heading, checks the preview's
field and curvature conventions against the fixture record, and verifies asset MIME types and exact
source bytes with identity and gzip requests. It follows fingerprinted asset
names through the .NET manifest and checks the fonts and vendor hashes.
To reproduce it locally:

```powershell
python tools/check_site_runtime.py --app web/HEPLab.Web/bin/Release/net10.0/HEPLab.Web.dll --content-root web/HEPLab.Web
python tools/check_site_runtime.py --app web/HEPLab.Web/bin/Release/net10.0/publish/HEPLab.Web.dll
```

## Source layout

- `HEPLab.Web/Pages/`: Razor Pages and the shared layout.
- `HEPLab.Web/Services/SiteContentService.cs`: Markdown loading, routing, navigation, and search data.
- `HEPLab.Web/Services/ExperimentPreviewService.cs`: reads fixed-fixture settings and provenance for the home event view.
- `HEPLab.Web/wwwroot/js/detector-view.js`: renders 3D fixture coordinates and declared surface envelopes with an interactive Canvas 2D camera; it runs no simulation.
- `HEPLab.Web/Pages/Shared/`: shared layout, navigation, preview, lab, and gallery partials.
- `HEPLab.Web/TagHelpers/`: reusable C# interface icons.
- `HEPLab.Web/Content/Docs/`: Markdown and MDX guide content.
- `HEPLab.Web/wwwroot/`: styles, scripts, branding, and standalone result exports.
- `docs/`: design, writing, architecture, and review notes for this app.
