using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

namespace UbMode.RoslynHost;

internal static class DocumentBuilder
{
    public static Document Parse(Request request)
    {
        var options = Options(request);
        var tree = CSharpSyntaxTree.ParseText(request.Source, options, request.Path ?? "");
        var coordinates = new TextCoordinates(request.Source);
        var nodes = new List<Node>();
        var syntaxNodes = new List<(SyntaxNode Syntax, int Id)>();
        BuildNodes(tree.GetRoot(), coordinates, nodes, syntaxNodes);
        return new Document(options.LanguageVersion.ToDisplayString(),
            tree.GetDiagnostics().Select(diagnostic => Describe(diagnostic, coordinates)).ToArray(),
            0, nodes, UnitExtractor.Extract(syntaxNodes, coordinates));
    }

    private static CSharpParseOptions Options(Request request)
    {
        var version = LanguageVersion.Default;
        if (request.LanguageVersion is string supplied && !LanguageVersionFacts.TryParse(supplied, out version))
            throw new ArgumentException($"Unknown C# language version: {supplied}");
        var options = new CSharpParseOptions(version, preprocessorSymbols: request.Symbols ?? []);
        return request.FileBasedProgram
            ? options.WithFeatures([new("FileBasedProgram", "true")])
            : options;
    }

    private static void BuildNodes(SyntaxNode root, TextCoordinates coordinates, List<Node> nodes,
        List<(SyntaxNode Syntax, int Id)> syntaxNodes)
    {
        var stack = new Stack<(SyntaxNodeOrToken Syntax, int Parent)>();
        stack.Push((root, -1));
        while (stack.TryPop(out var work))
        {
            var id = nodes.Count;
            nodes.Add(Describe(work.Syntax, coordinates));
            if (work.Parent >= 0) nodes[work.Parent].Children.Add(id);
            if (work.Syntax.AsNode() is not SyntaxNode syntax) continue;
            syntaxNodes.Add((syntax, id));
            foreach (var child in syntax.ChildNodesAndTokens().Reverse()) stack.Push((child, id));
        }
    }

    private static Node Describe(SyntaxNodeOrToken syntax, TextCoordinates coordinates)
    {
        var span = syntax.Span;
        var start = coordinates.Point(span.Start);
        var end = coordinates.Point(span.End);
        return new Node(((SyntaxKind)syntax.RawKind).ToString(), SyntaxRoles.For(syntax),
            coordinates.Byte(span.Start), coordinates.Byte(span.End), start.Line, end.Line,
            start.Column, end.Column, syntax.IsNode, []);
    }

    private static Diagnostic Describe(Microsoft.CodeAnalysis.Diagnostic diagnostic, TextCoordinates coordinates)
    {
        var span = diagnostic.Location.SourceSpan;
        var point = coordinates.Point(span.Start);
        return new Diagnostic(diagnostic.Id, diagnostic.GetMessage(), diagnostic.Severity.ToString().ToLowerInvariant(),
            point.Line, point.Column, coordinates.Byte(span.Start), coordinates.Byte(span.End));
    }
}
