using HEPLab.Web.Services;

var builder = WebApplication.CreateBuilder(args);
// A built DLL can also be previewed in Production before it is published.
// Load its asset manifest so compressed styles and scripts resolve in that mode.
builder.WebHost.UseStaticWebAssets();
builder.Services.AddRazorPages();
builder.Services.AddSingleton<SiteContentService>();
builder.Services.AddSingleton<ExperimentPreviewService>();

var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
    app.UseHsts();
}

app.UseStatusCodePagesWithReExecute("/not-found");
app.MapGet("/search-index.json", (SiteContentService content) => Results.Json(content.SearchIndex));
app.MapStaticAssets();
app.MapRazorPages().WithStaticAssets();

app.Run();
