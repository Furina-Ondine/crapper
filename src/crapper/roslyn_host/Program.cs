using System.Text;
using System.Text.Json;

namespace UbMode.RoslynHost;

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    private static int Main()
    {
        Console.InputEncoding = Encoding.UTF8;
        Console.OutputEncoding = new UTF8Encoding();
        try
        {
            while (Console.ReadLine() is string line)
            {
                var request = JsonSerializer.Deserialize<Request>(line, Json)
                    ?? throw new JsonException("A request must be a JSON object.");
                ArgumentNullException.ThrowIfNull(request.Source);
                var document = DocumentBuilder.Parse(request);
                Console.WriteLine(JsonSerializer.Serialize(document, Json));
                Console.Out.Flush();
            }
            return 0;
        }
        catch (Exception error) when (error is JsonException or ArgumentException)
        {
            Console.Error.WriteLine(error.Message);
            return 2;
        }
    }
}
