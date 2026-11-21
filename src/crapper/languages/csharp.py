"""C# executable units from the selected SDK's Roslyn parser."""

from dataclasses import dataclass

from crapper._roslyn import parse_source
from crapper.languages.treesitter import complexity
from crapper.model import Function


class SyntaxNode:
    """A Roslyn node or token with UTF-8 source coordinates."""

    def __init__(self, identity, item, data):
        self.id = identity
        self.kind = self.type = item["kind"]
        self.roles = frozenset(item["roles"])
        self.start_byte, self.end_byte = item["start"], item["end"]
        self.start_point = (item["startLine"] - 1, item["startColumn"])
        self.end_point = (item["endLine"] - 1, item["endColumn"])
        self.is_named = item["named"]
        self.parent = None
        self.children = []
        self._data = data

    @property
    def text(self):
        return self._data[self.start_byte:self.end_byte]

    @property
    def named_children(self):
        return [node for node in self.children if node.is_named]

    @property
    def child_count(self):
        return len(self.children)


@dataclass(frozen=True)
class Executable:
    """A scored unit and the original syntax nodes that it owns."""

    function: Function
    nodes: tuple[SyntaxNode, ...]
    private: bool


def _syntax_nodes(data, items):
    nodes = [SyntaxNode(index, item, data) for index, item in enumerate(items)]
    for node, item in zip(nodes, items):
        node.children = [nodes[index] for index in item["children"]]
        for child in node.children:
            child.parent = node
    return nodes


def _score(nodes):
    return 1 + sum(complexity(
        node, lambda current: "decision" in current.roles, lambda current: "type_scope" in current.roles,
    ) - 1 for node in nodes)


def _executable(item, nodes, path):
    syntax = tuple(nodes[index] for index in item["syntax"])
    return Executable(
        Function(
            name=item["name"],
            namespace=item["namespace"],
            complexity=_score(syntax),
            start_line=item["line"],
            end_line=item["endLine"],
            path=path,
            language="csharp",
            start_byte=item["start"],
            end_byte=item["end"],
        ),
        syntax,
        item["private"],
    )


def units_in_source(
    source: str, path: str, project_root: str | None = None
) -> tuple[bytes, list[Executable]]:
    """Return Roslyn's active executable members and original syntax."""

    document = parse_source(source, path, project_root)
    for diagnostic in document["diagnostics"]:
        if diagnostic["severity"] == "error":
            line, column = diagnostic["line"], diagnostic["column"] + 1
            code, message = diagnostic["code"], diagnostic["message"]
            raise SyntaxError(f"{path}:{line}:{column}: {code}: {message}")
    data = source.encode("utf-8")
    nodes = _syntax_nodes(data, document["nodes"])
    return data, [_executable(unit, nodes, path) for unit in document["units"]]


def functions_in_source(
    source: str, path: str, project_root: str | None = None
) -> list[Function]:
    _, units = units_in_source(source, path, project_root)
    return [unit.function for unit in units]
