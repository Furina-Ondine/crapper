"""Parser-independent source coordinates and executable units."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str
    start_byte: int
    end_byte: int
    start_line: int
    start_column: int


class SyntaxNode:
    """Native syntax kind plus shared roles; offsets and columns are UTF-8 bytes."""

    def __init__(self, identity, kind, roles, start, end, start_point, end_point, named):
        self.id = identity
        self.kind = self.type = kind
        self.roles = frozenset(roles)
        self.start_byte, self.end_byte = start, end
        self.start_point, self.end_point = start_point, end_point
        self.is_named = named
        self.parent = None
        self.children = []

    @property
    def named_children(self):
        return [node for node in self.children if node.is_named]

    @property
    def child_count(self):
        return len(self.children)

    def child_by_field_name(self, name):
        return None


@dataclass(frozen=True)
class ExecutableUnit:
    name: str
    namespace: str
    private: bool
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    syntax: tuple


@dataclass(frozen=True)
class ParsedDocument:
    root: object
    nodes: tuple
    units: tuple[ExecutableUnit, ...] = ()
    language_version: str | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


def compiler_document(payload):
    nodes = tuple(SyntaxNode(
        index, item["kind"], item["roles"], item["start"], item["end"],
        (item["startLine"] - 1, item["startColumn"]),
        (item["endLine"] - 1, item["endColumn"]), item["named"],
    ) for index, item in enumerate(payload["nodes"]))
    for node, item in zip(nodes, payload["nodes"]):
        node.children = [nodes[index] for index in item["children"]]
        for child in node.children:
            child.parent = node
    units = tuple(ExecutableUnit(
        item["name"], item["namespace"], item["private"], item["start"], item["end"],
        item["line"], item["endLine"], tuple(nodes[i] for i in item["syntax"]),
    ) for item in payload["units"])
    diagnostics = tuple(Diagnostic(
        item["code"], item["message"], item["severity"], item["start"], item["end"],
        item["line"], item["column"],
    ) for item in payload["diagnostics"])
    return ParsedDocument(nodes[payload["root"]], nodes, units, payload["languageVersion"], diagnostics)
