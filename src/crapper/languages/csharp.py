"""Executable C# members and their source ownership."""

from dataclasses import dataclass

from tree_sitter import Node

from crapper.languages.treesitter import (
    child_of_type,
    complexity,
    descendants,
    end_line,
    node_text,
    parse,
    start_line,
)
from crapper.model import Function

_TYPES = {
    "class_declaration",
    "enum_declaration",
    "interface_declaration",
    "record_declaration",
    "struct_declaration",
}
_METHODS = {
    "constructor_declaration",
    "conversion_operator_declaration",
    "destructor_declaration",
    "method_declaration",
    "operator_declaration",
}
_PROPERTIES = {"indexer_declaration", "property_declaration"}
_DECISIONS = {
    "and_pattern",
    "catch_clause",
    "catch_filter_clause",
    "conditional_expression",
    "do_statement",
    "foreach_statement",
    "for_statement",
    "if_statement",
    "or_pattern",
    "when_clause",
    "while_statement",
}
_ACCESS = {"private", "internal", "protected", "public"}


@dataclass(frozen=True)
class Executable:
    """A scored unit and the original syntax nodes that it owns."""

    function: Function
    nodes: tuple[Node, ...]
    private: bool


def _fallback_arm(node: Node) -> bool:
    pattern = node.named_children[0]
    while pattern.type == "parenthesized_pattern":
        pattern = pattern.named_children[0]
    return pattern.type == "discard" or (
        pattern.type == "declaration_pattern"
        and child_of_type(pattern, "implicit_type") is not None
    )


def _is_decision(node: Node) -> bool:
    if node.type in _DECISIONS:
        return True
    if node.type == "switch_section":
        return child_of_type(node, "case") is not None
    if node.type == "switch_expression_arm":
        return not _fallback_arm(node)
    operator = node.child_by_field_name("operator")
    return operator is not None and operator.type in {"&&", "||", "??", "??="}


def _is_type(node: Node) -> bool:
    return node.type in _TYPES


def _spelling(data: bytes, node: Node) -> str:
    return "".join(
        node_text(data, token).removeprefix("@")
        for token in descendants(node)
        if not token.child_count and token.type != "comment"
    )


def _namespace(data: bytes, member: Node, file_namespace: str) -> str:
    parts = []
    current = member.parent
    while current is not None:
        if current.type in _TYPES or current.type == "namespace_declaration":
            parts.append(_spelling(data, current.child_by_field_name("name")))
        current = current.parent
    return ".".join(part for part in (file_namespace, *reversed(parts)) if part)


def _qualified_name(data: bytes, member: Node) -> str:
    specifier = child_of_type(member, "explicit_interface_specifier")
    prefix = _spelling(data, specifier) if specifier is not None else ""
    name = member.child_by_field_name("name")
    return prefix + (_spelling(data, name) if name is not None else "this")


def _member_name(data: bytes, member: Node) -> str:
    if member.type == "accessor_declaration":
        owner = member.parent.parent
        return f"{_qualified_name(data, owner)}.{_qualified_name(data, member)}"
    if member.type == "operator_declaration":
        return "operator " + _spelling(data, member.child_by_field_name("operator"))
    if member.type == "conversion_operator_declaration":
        kind = child_of_type(member, "implicit", "explicit").type
        return f"{kind} operator {_spelling(data, member.child_by_field_name('type'))}"
    name = _qualified_name(data, member)
    if member.type in _PROPERTIES:
        return f"{name}.get"
    if member.type == "destructor_declaration":
        return f"~{name}"
    return name


def _is_private(data: bytes, member: Node) -> bool:
    owner = member.parent.parent if member.type == "accessor_declaration" else member
    for node in (member, owner) if member != owner else (member,):
        if child_of_type(node, "explicit_interface_specifier") is not None:
            return True
        access = _ACCESS.intersection(
            node_text(data, child) for child in node.named_children if child.type == "modifier"
        )
        if access:
            return access == {"private"}
    current = owner.parent
    while current is not None:
        if _is_type(current):
            return current.type != "interface_declaration"
        current = current.parent
    return True


def _has_body(node: Node) -> bool:
    if node.type in _METHODS or node.type == "accessor_declaration":
        return node.child_by_field_name("body") is not None
    if node.type in _PROPERTIES:
        value = node.child_by_field_name("value")
        return value is not None and value.type == "arrow_expression_clause"
    return False


def _unit(
    nodes: tuple[Node, ...], path: str, namespace: str, name: str, private: bool
) -> Executable:
    first, last = nodes[0], nodes[-1]
    score = 1 + sum(complexity(node, _is_decision, _is_type) - 1 for node in nodes)
    return Executable(
        function=Function(
            name=name,
            namespace=namespace,
            complexity=score,
            start_line=start_line(first),
            end_line=end_line(last),
            path=path,
            language="csharp",
            start_byte=first.start_byte,
            end_byte=last.end_byte,
        ),
        nodes=nodes,
        private=private,
    )


def _check_syntax(root: Node, path: str) -> None:
    if not root.has_error:
        return
    issue = next((node for node in descendants(root) if node.is_error or node.is_missing), root)
    row, column = issue.start_point
    raise SyntaxError(f"{path}:{row + 1}:{column + 1}: Tree-sitter could not parse C# syntax")


def _top_level_statements(root: Node):
    pending = list(reversed(root.named_children))
    while pending:
        node = pending.pop()
        if node.type in {"preproc_if", "preproc_elif", "preproc_else"}:
            # A top-level conditional wraps bare statements instead of global_statement nodes.
            condition = node.child_by_field_name("condition")
            pending.extend(child for child in reversed(node.named_children) if child != condition)
        elif node.type == "block" or node.type.endswith("_statement"):
            yield node


def units_in_source(
    source: str, path: str, project_root: str | None = None
) -> tuple[bytes, list[Executable]]:
    """Return one owner per executable member, including the top-level program."""

    del project_root
    data, tree = parse(source, "csharp")
    root = tree.root_node
    _check_syntax(root, path)
    scope = child_of_type(root, "file_scoped_namespace_declaration")
    file_namespace = _spelling(data, scope.child_by_field_name("name")) if scope else ""
    statements = tuple(_top_level_statements(root))
    found = []
    if statements:
        found.append(_unit(statements, path, "Program", "<top-level>", False))
    pending = list(reversed(root.named_children))
    while pending:
        member = pending.pop()
        if _has_body(member):
            found.append(_unit(
                (member,), path, _namespace(data, member, file_namespace),
                _member_name(data, member), _is_private(data, member),
            ))
        elif member.type != "global_statement":
            pending.extend(reversed(member.named_children))
    return data, sorted(found, key=lambda unit: unit.function.start_byte)


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    _, units = units_in_source(source, path, project_root)
    return [unit.function for unit in units]
