using HEPLab.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace HEPLab.Web.Pages;

public sealed class DocsModel(SiteContentService content) : PageModel
{
    [FromRoute]
    public string? Slug { get; set; }
    public SitePage? Doc { get; private set; }
    public bool Found => Doc is not null;
    public NavigationLink? Previous { get; private set; }
    public NavigationLink? Next { get; private set; }
    public string SourcePath { get; private set; } = "";
    public string Category { get; private set; } = "Guide";
    public int ReadingMinutes { get; private set; }

    public IActionResult OnGet()
    {
        Doc = content.Find(Slug);
        if (Doc is null) return NotFound();
        ViewData["Title"] = Doc.Title;
        ViewData["Description"] = Doc.Description;
        Category = content.Navigation.FirstOrDefault(group => group.Links.Any(link => link.Url == Doc.Url))?.Title ?? "Guide";
        ReadingMinutes = Math.Max(1, (int)Math.Ceiling(Doc.PlainText.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length / 220.0));
        var links = content.Navigation.SelectMany(group => group.Links).Where(link => link.Url != "/").ToArray();
        var index = Array.FindIndex(links, link => link.Url == Doc.Url);
        Previous = index > 0 ? links[index - 1] : null;
        Next = index >= 0 && index + 1 < links.Length ? links[index + 1] : null;
        SourcePath = Doc.Url.Trim('/') + ".md";
        if (Doc.Url == "/education/") SourcePath = "education.mdx";
        if (Doc.Url == "/gallery/") SourcePath = "gallery.mdx";
        if (Doc.Url == "/results/") SourcePath = "results.mdx";
        return base.Page();
    }
}
