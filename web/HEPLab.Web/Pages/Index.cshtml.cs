using Microsoft.AspNetCore.Mvc.RazorPages;
using HEPLab.Web.Services;

namespace HEPLab.Web.Pages;

public sealed class IndexModel(ExperimentPreviewService experiment) : PageModel
{
    public ExperimentPreviewService Experiment { get; } = experiment;
    public void OnGet() { }
}
