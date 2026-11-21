namespace UbMode.RoslynHost;

internal sealed record Request(string Path, string Source, string? LanguageVersion,
    string[]? Symbols, bool FileBasedProgram = false);

internal sealed record Document(string LanguageVersion, IReadOnlyList<Diagnostic> Diagnostics,
    int Root, IReadOnlyList<Node> Nodes, IReadOnlyList<Unit> Units);

internal sealed record Diagnostic(string Code, string Message, string Severity,
    int Line, int Column, int Start, int End);

internal sealed record Node(string Kind, IReadOnlyList<string> Roles, int Start, int End,
    int StartLine, int EndLine, int StartColumn, int EndColumn, bool Named, List<int> Children);

internal sealed record Unit(string Name, string Namespace, bool Private, int Start, int End,
    int Line, int EndLine, IReadOnlyList<int> Syntax);
