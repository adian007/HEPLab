# HEPLab website and desktop architecture

The public guide is an ASP.NET Core Razor Pages app targeting .NET 10. Markdown
content is rendered with Markdig. It remains separate from the local Python
simulator and its FastAPI service.

Run it from the repository root:

```powershell
dotnet run --project web/HEPLab.Web
dotnet build web/HEPLab.Web/HEPLab.Web.csproj
dotnet publish web/HEPLab.Web/HEPLab.Web.csproj --configuration Release
```

See the following chapters for the information architecture, frontend, backend
boundary, desktop shell, event display, and delivery plan.

| File | Scope |
|---|---|
| [Product and information architecture](01-product-and-information-architecture.md) | Readers, page groups, and product boundary |
| [Frontend architecture](02-frontend-architecture.md) | Razor Pages, Markdown content, navigation, and search |
| [Backend and API boundary](03-backend-and-api.md) | Public guide compared with the local Python service |
| [Desktop packaging](04-desktop-packaging.md) | Desktop workbench shell and supervised worker |
| [Event display](05-event-display.md) | Local result display and its evidence boundary |
| [Delivery plan](06-delivery-plan.md) | Hosting and maintenance path |
