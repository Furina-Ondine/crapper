using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace UbMode.RoslynHost;

internal static class SyntaxRoles
{
    private static readonly (string Role, Func<SyntaxNode, bool> Matches)[] NodeRules =
    [
        ("identifier", node => node is IdentifierNameSyntax),
        ("literal", node => node is LiteralExpressionSyntax or InterpolatedStringTextSyntax),
        ("call", node => node is InvocationExpressionSyntax or BaseObjectCreationExpressionSyntax),
        ("callee", IsCallee),
        ("member_access", node => node is MemberAccessExpressionSyntax or MemberBindingExpressionSyntax),
        ("name_path", node => node is GenericNameSyntax or QualifiedNameSyntax or AliasQualifiedNameSyntax),
        ("type_arguments", node => node is TypeArgumentListSyntax or TypeParameterListSyntax),
        ("arguments", node => node is BaseArgumentListSyntax),
        ("statement", node => node is StatementSyntax),
        ("declaration", node => node is MemberDeclarationSyntax or AccessorDeclarationSyntax or VariableDeclarationSyntax),
        ("metadata", node => node is AttributeListSyntax),
        ("binary", node => node is BinaryExpressionSyntax or RelationalPatternSyntax or BinaryPatternSyntax),
        ("unary", node => node is PrefixUnaryExpressionSyntax or UnaryPatternSyntax),
        ("decision", IsDecision),
        ("type_scope", node => node is BaseTypeDeclarationSyntax),
        ("group", node => node is ParenthesizedExpressionSyntax or ParenthesizedPatternSyntax)
    ];

    private static readonly HashSet<SyntaxKind> Decisions =
    [
        SyntaxKind.IfStatement, SyntaxKind.ForStatement, SyntaxKind.ForEachStatement,
        SyntaxKind.ForEachVariableStatement, SyntaxKind.WhileStatement, SyntaxKind.DoStatement,
        SyntaxKind.CatchClause, SyntaxKind.ConditionalExpression, SyntaxKind.LogicalAndExpression,
        SyntaxKind.LogicalOrExpression, SyntaxKind.CoalesceExpression, SyntaxKind.CoalesceAssignmentExpression,
        SyntaxKind.AndPattern, SyntaxKind.OrPattern, SyntaxKind.WhenClause, SyntaxKind.CatchFilterClause,
        SyntaxKind.CaseSwitchLabel, SyntaxKind.CasePatternSwitchLabel
    ];

    private static readonly HashSet<SyntaxKind> Operators =
    [
        SyntaxKind.PlusToken, SyntaxKind.MinusToken, SyntaxKind.AsteriskToken, SyntaxKind.SlashToken,
        SyntaxKind.PercentToken, SyntaxKind.EqualsEqualsToken, SyntaxKind.ExclamationEqualsToken,
        SyntaxKind.LessThanToken, SyntaxKind.GreaterThanToken, SyntaxKind.LessThanEqualsToken,
        SyntaxKind.GreaterThanEqualsToken, SyntaxKind.AmpersandAmpersandToken, SyntaxKind.BarBarToken,
        SyntaxKind.AmpersandToken, SyntaxKind.BarToken, SyntaxKind.CaretToken, SyntaxKind.ExclamationToken,
        SyntaxKind.TildeToken, SyntaxKind.LessThanLessThanToken, SyntaxKind.GreaterThanGreaterThanToken,
        SyntaxKind.GreaterThanGreaterThanGreaterThanToken, SyntaxKind.PlusEqualsToken,
        SyntaxKind.MinusEqualsToken, SyntaxKind.AsteriskEqualsToken, SyntaxKind.SlashEqualsToken,
        SyntaxKind.PercentEqualsToken, SyntaxKind.AmpersandEqualsToken, SyntaxKind.BarEqualsToken,
        SyntaxKind.CaretEqualsToken, SyntaxKind.LessThanLessThanEqualsToken,
        SyntaxKind.GreaterThanGreaterThanEqualsToken, SyntaxKind.GreaterThanGreaterThanGreaterThanEqualsToken,
        SyntaxKind.PlusPlusToken, SyntaxKind.MinusMinusToken, SyntaxKind.QuestionQuestionToken,
        SyntaxKind.QuestionQuestionEqualsToken, SyntaxKind.EqualsGreaterThanToken,
        SyntaxKind.QuestionToken, SyntaxKind.EqualsToken, SyntaxKind.AndKeyword,
        SyntaxKind.OrKeyword, SyntaxKind.NotKeyword
    ];

    public static IReadOnlyList<string> For(SyntaxNodeOrToken syntax)
    {
        if (syntax.AsNode() is SyntaxNode node)
            return NodeRules.Where(rule => rule.Matches(node)).Select(rule => rule.Role).ToArray();
        return TokenRoles(syntax.AsToken());
    }

    private static IReadOnlyList<string> TokenRoles(SyntaxToken token)
    {
        var roles = new List<string>();
        if (token.IsKind(SyntaxKind.IdentifierToken)) roles.Add("identifier");
        if (token.Parent is LiteralExpressionSyntax || token.IsKind(SyntaxKind.InterpolatedStringTextToken))
            roles.Add("literal");
        if (token.IsKind(SyntaxKind.NumericLiteralToken)) roles.Add("number");
        if (IsBooleanLiteral(token)) roles.Add("boolean");
        if (Operators.Contains(token.Kind())) roles.Add("operator");
        return roles;
    }

    private static bool IsDecision(SyntaxNode node)
    {
        if (Decisions.Contains(node.Kind())) return true;
        return node is SwitchExpressionArmSyntax arm && !IsDefaultPattern(arm.Pattern);
    }

    private static bool IsBooleanLiteral(SyntaxToken token) => token.Parent is LiteralExpressionSyntax &&
        (token.IsKind(SyntaxKind.TrueKeyword) || token.IsKind(SyntaxKind.FalseKeyword));

    private static bool IsCallee(SyntaxNode node) => node.Parent switch
    {
        InvocationExpressionSyntax call => call.Expression == node,
        ObjectCreationExpressionSyntax creation => creation.Type == node,
        _ => false
    };

    private static bool IsDefaultPattern(PatternSyntax pattern)
    {
        while (pattern is ParenthesizedPatternSyntax group) pattern = group.Pattern;
        return pattern is DiscardPatternSyntax or VarPatternSyntax;
    }
}
