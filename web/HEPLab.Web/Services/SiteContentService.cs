using System.Text.RegularExpressions;
using System.Net;
using Markdig;

namespace HEPLab.Web.Services;

public sealed record NavigationLink(string Title, string Url);
public sealed record NavigationGroup(string Title, IReadOnlyList<NavigationLink> Links);
public sealed record TocLink(string Title, string Id);
public sealed record PageEmbed(string PartialName, string BeforeHtml, string AfterHtml);
public sealed record SitePage(string Title, string Description, string Url, string Html, string PlainText, IReadOnlyList<TocLink> Toc, PageEmbed? Embed);
public sealed record SearchDocument(string Title, string Description, string Url, string Text);

public sealed class SiteContentService
{
    private static readonly Regex FrontMatter = new(@"\A\uFEFF?---\s*\r?\n(?<meta>[\s\S]*?)\r?\n---\s*\r?\n(?<body>[\s\S]*)\z", RegexOptions.Compiled);
    private static readonly Regex Tags = new("<[^>]+>", RegexOptions.Compiled);
    private static readonly Regex RenderedHeading = new(
        "<h[2-6]\\b[^>]*\\bid=\"(?<id>[^\"]+)\"[^>]*>(?<title>[\\s\\S]*?)</h[2-6]>",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly MarkdownPipeline Pipeline = new MarkdownPipelineBuilder()
        .UseAdvancedExtensions()
        .DisableHtml()
        .UseAutoIdentifiers()
        .Build();

    private static readonly NavigationGroup[] Groups =
    [
        new("Start here", [new("HEPLab overview", "/"), new("Getting started", "/getting-started/")]),
        new("Project", [new("Capabilities", "/project/capabilities/"), new("Roadmap", "/project/roadmap/"), new("Known limitations", "/project/limitations/")]),
        new("Use HEPLab", [new("Local workbench", "/simulation/workbench/"), new("Simulation models and fidelity", "/simulation/models/"), new("CERN Open Data", "/data/open-data/"), new("Analysis workflow", "/analysis/workflow/"), new("Rediscover the Z boson", "/education/"), new("Share and inspect results", "/results/"), new("Results gallery", "/gallery/")]),
        new("Evidence", [new("Validation evidence", "/validation/evidence/"), new("How to read a result", "/validation/reading-results/")]),
        new("Reference", [new("Architecture", "/architecture/"), new("Local API reference", "/reference/api/"), new("Python API v1", "/reference/python-api-v1/"), new("Contributing", "/contributing/"), new("Frequently asked questions", "/faq/")]),
    ];

    private readonly IReadOnlyDictionary<string, SitePage> _pages;

    public SiteContentService(IWebHostEnvironment environment)
    {
        var docsRoot = Path.Combine(environment.ContentRootPath, "Content", "Docs");
        var pages = new Dictionary<string, SitePage>(StringComparer.OrdinalIgnoreCase);
        foreach (var path in Directory.EnumerateFiles(docsRoot, "*.*", SearchOption.AllDirectories)
                     .Where(path => path.EndsWith(".md", StringComparison.OrdinalIgnoreCase) || path.EndsWith(".mdx", StringComparison.OrdinalIgnoreCase)))
        {
            var relative = Path.GetRelativePath(docsRoot, path).Replace('\\', '/');
            if (relative.Equals("index.mdx", StringComparison.OrdinalIgnoreCase) || relative.Equals("index.md", StringComparison.OrdinalIgnoreCase)) continue;
            var withoutExtension = Regex.Replace(relative, @"\.(md|mdx)$", "", RegexOptions.IgnoreCase);
            var url = "/" + withoutExtension + "/";
            var page = ParsePage(url, File.ReadAllText(path));
            pages[url] = page;
        }
        _pages = pages;
    }

    public IReadOnlyList<NavigationGroup> Navigation => Groups
        .Select(group => group with { Links = group.Links.Where(link => link.Url == "/" || _pages.ContainsKey(link.Url)).ToArray() })
        .ToArray();

    public SitePage? Find(string? slug)
    {
        var key = "/" + (slug ?? "").Trim('/') + "/";
        return _pages.GetValueOrDefault(key);
    }

    public IReadOnlyList<SearchDocument> SearchIndex => _pages.Values
        .Select(page => new SearchDocument(page.Title, page.Description, page.Url, page.PlainText))
        .Prepend(new SearchDocument("HEPLab", "Local particle simulation and analysis with CERN Open Data.", "/", "HEPLab local particle simulation CERN Open Data workbench analysis validation guide"))
        .ToArray();

    private static SitePage ParsePage(string url, string raw)
    {
        var match = FrontMatter.Match(raw);
        var metadata = match.Success ? match.Groups["meta"].Value : "";
        var markdown = match.Success ? match.Groups["body"].Value : raw;
        var title = ReadMeta(metadata, "title") ?? "HEPLab guide";
        var description = ReadMeta(metadata, "description") ?? "HEPLab project guide.";

        markdown = Regex.Replace(markdown, @"^import\s+.*(?:@astrojs/starlight/components|\.astro').*\r?\n", "", RegexOptions.Multiline);
        markdown = Regex.Replace(markdown, @"<code>([\s\S]*?)</code>", match => "`" + match.Groups[1].Value + "`", RegexOptions.IgnoreCase);
        markdown = Regex.Replace(markdown, @"<Aside\b[^>]*title=""(?<title>[^""]+)""[^>]*>(?<body>[\s\S]*?)</Aside>", m =>
        {
            var body = m.Groups["body"].Value.Trim().Replace("\r", "");
            var lines = body.Split('\n').Select(line => "> " + line.Trim()).ToList();
            return "> **" + m.Groups["title"].Value + "**\n>\n" + string.Join("\n", lines);
        }, RegexOptions.Singleline);
        markdown = Regex.Replace(markdown, @"<LinkCard\s+title=""(?<title>[^""]+)""\s+href=""(?<href>[^""]+)""\s+description=""(?<description>[^""]*)""\s*/>", m =>
            $"[**{m.Groups["title"].Value}**]({m.Groups["href"].Value})\n\n{m.Groups["description"].Value}");
        markdown = Regex.Replace(markdown, @"</?CardGrid\s*>", "");
        var labToken = "HEPLABTRUSTEDLAB" + Guid.NewGuid().ToString("N");
        var galleryToken = "HEPLABTRUSTEDGALLERY" + Guid.NewGuid().ToString("N");
        markdown = markdown.Replace("<ZBosonLab />", labToken, StringComparison.Ordinal)
                           .Replace("<ResultGallery />", galleryToken, StringComparison.Ordinal);

        var html = Markdown.ToHtml(markdown, Pipeline);
        PageEmbed? embed = null;
        foreach (var (token, partial) in new[] { (labToken, "_ZBosonLab"), (galleryToken, "_ResultGallery") })
        {
            var marker = "<p>" + token + "</p>";
            var at = html.IndexOf(marker, StringComparison.Ordinal);
            if (at < 0) continue;
            embed = new PageEmbed(partial, html[..at], html[(at + marker.Length)..]);
            html = embed.BeforeHtml + embed.AfterHtml;
            break;
        }
        var toc = RenderedHeading.Matches(html)
            .Select(match => new TocLink(
                WebUtility.HtmlDecode(Tags.Replace(match.Groups["title"].Value, " ")).Trim(),
                WebUtility.HtmlDecode(match.Groups["id"].Value)))
            .Where(item => item.Title.Length > 0)
            .ToArray();
        var plain = Tags.Replace(Regex.Replace(markdown, @"```[\s\S]*?```|`([^`]+)`", " $1 "), " ");
        plain = Regex.Replace(plain, @"[\[\]!*_>#|]", " ");
        plain = Regex.Replace(plain, @"\s+", " ").Trim();
        return new SitePage(title, description, url, html, plain, toc, embed);
    }

    private static string? ReadMeta(string metadata, string key)
    {
        var match = Regex.Match(metadata, "^" + Regex.Escape(key) + @":\s*(?:""(?<quoted>[^""]*)""|'(?<single>[^']*)'|(?<plain>[^\r\n]+))\s*$", RegexOptions.Multiline);
        return match.Success ? match.Groups.Cast<Group>().Skip(1).FirstOrDefault(group => group.Success)?.Value.Trim() : null;
    }

}
