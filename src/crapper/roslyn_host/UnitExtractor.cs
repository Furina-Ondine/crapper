using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace UbMode.RoslynHost;

internal static class UnitExtractor
{
    public static IReadOnlyList<Unit> Extract(IReadOnlyList<(SyntaxNode Syntax, int Id)> nodes,
        TextCoordinates coordinates)
    {
        var units = TopLevel(nodes, coordinates);
        foreach (var (node, id) in nodes)
        {
            if (!HasBody(node) || HasExecutableAncestor(node)) continue;
            units.Add(new Unit(Name(node), Namespace(node), IsPrivate(node),
                coordinates.Byte(node.SpanStart), coordinates.Byte(node.Span.End),
                coordinates.Point(node.SpanStart).Line, coordinates.InclusiveEndLine(node.Span), [id]));
        }
        return units.OrderBy(unit => unit.Start).ToArray();
    }

    private static List<Unit> TopLevel(IReadOnlyList<(SyntaxNode Syntax, int Id)> nodes, TextCoordinates coordinates)
    {
        var statements = nodes.Where(entry => entry.Syntax is GlobalStatementSyntax).ToArray();
        if (statements.Length == 0) return [];
        var first = statements[0].Syntax;
        var last = statements[^1].Syntax;
        return [new Unit("<top-level>", "Program", false,
            coordinates.Byte(first.SpanStart), coordinates.Byte(last.Span.End),
            coordinates.Point(first.SpanStart).Line, coordinates.InclusiveEndLine(last.Span),
            statements.Select(entry => entry.Id).ToArray())];
    }

    private static bool HasExecutableAncestor(SyntaxNode node) => node.Ancestors().Any(HasBody);

    private static bool HasBody(SyntaxNode node) => node switch
    {
        BaseMethodDeclarationSyntax method => method.Body is not null || method.ExpressionBody is not null,
        AccessorDeclarationSyntax accessor => accessor.Body is not null || accessor.ExpressionBody is not null,
        PropertyDeclarationSyntax property => property.ExpressionBody is not null,
        IndexerDeclarationSyntax indexer => indexer.ExpressionBody is not null,
        _ => false
    };

    private static string Name(SyntaxNode node) => node switch
    {
        MethodDeclarationSyntax method => Qualify(method.ExplicitInterfaceSpecifier, method.Identifier.ValueText),
        ConstructorDeclarationSyntax constructor => constructor.Identifier.ValueText,
        DestructorDeclarationSyntax destructor => "~" + destructor.Identifier.ValueText,
        OperatorDeclarationSyntax operation => "operator " + operation.OperatorToken.Text,
        ConversionOperatorDeclarationSyntax conversion => conversion.ImplicitOrExplicitKeyword.ValueText + " operator " + conversion.Type,
        AccessorDeclarationSyntax accessor => PropertyName(accessor.Parent?.Parent) + "." + accessor.Keyword.ValueText,
        BasePropertyDeclarationSyntax property => PropertyName(property) + ".get",
        _ => throw new ArgumentException("The syntax node is not an executable member.")
    };

    private static string PropertyName(SyntaxNode? node) => node switch
    {
        PropertyDeclarationSyntax property => Qualify(property.ExplicitInterfaceSpecifier, property.Identifier.ValueText),
        IndexerDeclarationSyntax indexer => Qualify(indexer.ExplicitInterfaceSpecifier, "this"),
        EventDeclarationSyntax eventDeclaration => Qualify(eventDeclaration.ExplicitInterfaceSpecifier, eventDeclaration.Identifier.ValueText),
        _ => throw new ArgumentException("An accessor must belong to a property, indexer or event.")
    };

    private static string Qualify(ExplicitInterfaceSpecifierSyntax? specifier, string name) =>
        specifier is null ? name : Spelling(specifier.Name) + "." + name;

    private static string Spelling(SyntaxNode name) => string.Concat(name.DescendantTokens().Select(token => token.ValueText));

    private static string Namespace(SyntaxNode node)
    {
        var parts = node.Ancestors().Reverse().Select(ancestor => ancestor switch
        {
            BaseNamespaceDeclarationSyntax space => Spelling(space.Name),
            BaseTypeDeclarationSyntax type => type.Identifier.ValueText,
            _ => null
        });
        return string.Join(".", parts.Where(part => part is not null));
    }

    private static SyntaxTokenList Modifiers(SyntaxNode node) => node switch
    {
        BaseMethodDeclarationSyntax method => method.Modifiers,
        BasePropertyDeclarationSyntax property => property.Modifiers,
        AccessorDeclarationSyntax accessor => accessor.Modifiers,
        _ => default
    };

    private static bool IsPrivate(SyntaxNode node)
    {
        var modifiers = Modifiers(node);
        if (modifiers.Any(SyntaxKind.PrivateKeyword)) return true;
        if (modifiers.Any(token => token.IsKind(SyntaxKind.PublicKeyword) || token.IsKind(SyntaxKind.ProtectedKeyword) || token.IsKind(SyntaxKind.InternalKeyword)))
            return false;
        if (node is AccessorDeclarationSyntax && node.Parent?.Parent is SyntaxNode property) return IsPrivate(property);
        return node.Ancestors().OfType<BaseTypeDeclarationSyntax>().FirstOrDefault() is not InterfaceDeclarationSyntax;
    }
}
