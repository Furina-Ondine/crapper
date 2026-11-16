"""Score compiler-provided executable units with the shared complexity walk."""

from crapper.model import Function


def _score(unit):
    from crapper.languages.treesitter import complexity

    return 1 + sum(complexity(
        node, lambda item: "decision" in item.roles,
        lambda item: "type_scope" in item.roles,
    ) - 1 for node in unit.syntax)


def functions_in_source(source, path, project_root=None):
    from crapper.frontend import parse_document

    document = parse_document(source, "csharp", path, project_root=project_root)
    return [Function(
        name=unit.name, namespace=unit.namespace, complexity=_score(unit),
        start_line=unit.start_line, end_line=unit.end_line, path=path, language="csharp",
        start_byte=unit.start_byte, end_byte=unit.end_byte, private=unit.private,
    ) for unit in document.units]
