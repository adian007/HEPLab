# Frontend architecture

The project guide is an ASP.NET Core Razor Pages application. Markdig renders
the Markdown and MDX documents in `web/HEPLab.Web/Content/Docs/`. Razor Pages
provides route handling and a shared layout. The app serves `/search-index.json`
from the same content source, so keyboard search works in development and in
production.

```text
web/HEPLab.Web/
├── Pages/                         Razor pages and shared layout
├── Services/SiteContentService.cs Markdown rendering, route map, nav, search data
├── Content/Docs/                  Markdown and MDX project guide
└── wwwroot/                       CSS, JavaScript, logo, offline examples
```

The home page is `Pages/Index.cshtml`. Curated sidebar groups are configured in
`Services/SiteContentService.cs`. Site-wide behavior is plain JavaScript in
`wwwroot/js/`; the interactive lab and gallery use their own small scripts.

## Content conventions

Add each guide page under `Content/Docs/` with a `title` and `description` in
YAML front matter. The relative filename defines the route: for example,
`simulation/models.md` becomes `/simulation/models/`. Add pages to the curated
navigation in `SiteContentService.cs` when they should appear in the sidebar.

Page content remains authored Markdown. Keep technical claims tied to the
engineering handbook and distinguish code execution evidence from physics
validation.

## Build and review

```powershell
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

Use `dotnet run --project web/HEPLab.Web` for browser review. The published
application requires an ASP.NET Core 10 host. It does not run or proxy the
simulator API.
