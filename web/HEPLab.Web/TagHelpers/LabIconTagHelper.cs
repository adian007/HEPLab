using Microsoft.AspNetCore.Razor.TagHelpers;

namespace HEPLab.Web.TagHelpers;

/// <summary>Shared decorative icons. Control labels remain in visible text.</summary>
[HtmlTargetElement("lab-icon")]
public sealed class LabIconTagHelper : TagHelper
{
    public string Name { get; set; } = "arrow-right";
    private static readonly IReadOnlyDictionary<string, string> Paths = new Dictionary<string, string>
    {
        ["arrow-right"] = "<path d='M4 12h16m-6-6 6 6-6 6'/>",
        ["arrow-up-right"] = "<path d='M6 18 18 6M6 6h12v12'/>",
        ["chevron-right"] = "<path d='m9 5 7 7-7 7'/>",
        ["search"] = "<circle cx='10.5' cy='10.5' r='6.5'/><path d='m16 16 4.5 4.5'/>",
        ["menu"] = "<path d='M4 7h16M4 12h16M4 17h16'/>",
        ["close"] = "<path d='m6 6 12 12M6 18 18 6'/>",
        ["book"] = "<path d='M12 5v16M3 3c4 0 6 0 9 2 3-2 5-2 9-2v16c-4 0-6 0-9 2-3-2-5-2-9-2Z'/>",
        ["flask"] = "<path d='M9 3h6M10 3v6L4 19a1.3 1.3 0 0 0 1 2h14a1.3 1.3 0 0 0 1-2L14 9V3M7.5 14h9'/>",
        ["layers"] = "<path d='m12 3 10 5-10 5L2 8Zm-9 9 9 5 9-5M3 16l9 5 9-5'/>",
        ["terminal"] = "<rect x='3' y='4' width='18' height='16' rx='2'/><path d='m7 9 3 3-3 3m6 0h4'/>",
        ["source"] = "<path d='m8 5-6 7 6 7m8-14 6 7-6 7m-3-16-2 18'/>",
        ["shield"] = "<path d='m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Zm-4 9 3 3 5-5'/>",
        ["copy"] = "<rect x='8' y='8' width='12' height='13' rx='2'/><path d='M16 8V3H3v13h5'/>",
        ["check"] = "<path d='m5 12 4 4L19 6'/>",
        ["download"] = "<path d='M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5'/>",
        ["orbit"] = "<circle cx='12' cy='12' r='3'/><ellipse cx='12' cy='12' rx='11' ry='5' transform='rotate(-35 12 12)'/>",
    };
    public override void Process(TagHelperContext context, TagHelperOutput output)
    {
        output.TagName = "svg";
        output.TagMode = TagMode.StartTagAndEndTag;
        output.Attributes.SetAttribute("class", $"icon {output.Attributes["class"]?.Value}".Trim());
        output.Attributes.SetAttribute("viewBox", "0 0 24 24");
        output.Attributes.SetAttribute("width", "20");
        output.Attributes.SetAttribute("height", "20");
        output.Attributes.SetAttribute("fill", "none");
        output.Attributes.SetAttribute("stroke", "currentColor");
        output.Attributes.SetAttribute("stroke-width", "1.6");
        output.Attributes.SetAttribute("stroke-linecap", "round");
        output.Attributes.SetAttribute("stroke-linejoin", "round");
        output.Attributes.SetAttribute("aria-hidden", "true");
        output.Attributes.SetAttribute("focusable", "false");
        output.Content.SetHtmlContent(Paths[Name]);
    }
}
