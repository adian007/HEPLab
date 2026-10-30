using System.Globalization;
using System.Text.Json;

namespace HEPLab.Web.Services;

/// <summary>Reads provenance and declared settings for the fixed, synthetic home-page event.</summary>
public sealed class ExperimentPreviewService
{
    public const string FixtureUrl = "/examples/analytic-muon-pair-result-v1.json";
    public string FieldTesla { get; }
    public string MomentumGeV { get; }
    public string ResultDigest { get; }
    public string GeometryId { get; }
    public int EventIndex { get; }

    private static string Number(double value) => value.ToString("0.###", CultureInfo.InvariantCulture);

    public ExperimentPreviewService(IWebHostEnvironment environment)
    {
        var file = environment.WebRootFileProvider.GetFileInfo(FixtureUrl.TrimStart('/'));
        using var stream = file.CreateReadStream();
        using var document = JsonDocument.Parse(stream);
        var root = document.RootElement;
        if (!root.GetProperty("artifact").GetProperty("static_fixture").GetBoolean())
            throw new InvalidDataException("The home preview requires an explicitly synthetic fixture.");

        FieldTesla = Number(root.GetProperty("config").GetProperty("bz_tesla").GetDouble());
        MomentumGeV = Number(root.GetProperty("config").GetProperty("momentum_gev").GetDouble());
        EventIndex = root.GetProperty("event").GetInt32();
        ResultDigest = root.GetProperty("artifact").GetProperty("result_sha256").GetString()!;
        GeometryId = root.GetProperty("geometry").GetProperty("id").GetString()!;
    }
}
