"""One syntax boundary for compiler and tree-sitter providers.

Consumers use roles for shared operations and retain native kinds for language
operations. C# syntax errors are reported rather than silently approximated.
"""

from functools import lru_cache

from crapper.languages.treesitter import parse
from crapper.syntax import ParsedDocument, compiler_document


_ROLE_TYPES = {
    "binary": {"binary_expression", "binary_operator", "comparison_operator", "boolean_operator"},
    "unary": {"unary_expression", "unary_operator", "not_operator", "comparison_operator"},
    "number": {"number", "number_literal", "integer", "integer_literal", "int_literal",
               "float", "float_literal", "decimal_integer_literal", "num_lit"},
    "boolean": {"true", "false", "True", "False", "bool_lit"},
}


def _roles(node):
    roles = {role for role, kinds in _ROLE_TYPES.items() if node.type in kinds}
    for role in ("statement", "declaration"):
        if node.type.endswith("_" + role):
            roles.add(role)
    return roles


class NodeView:
    """Keep tree-sitter field access and stable identity behind the common API."""

    def __init__(self, node, cache):
        self._node, self._cache = node, cache
        self.roles = frozenset(_roles(node))

    def _wrap(self, node):
        if node is None:
            return None
        if node.id not in self._cache:
            self._cache[node.id] = NodeView(node, self._cache)
        return self._cache[node.id]

    @property
    def kind(self):
        return self._node.type

    @property
    def parent(self):
        return self._wrap(self._node.parent)

    @property
    def children(self):
        return [self._wrap(node) for node in self._node.children]

    @property
    def named_children(self):
        return [self._wrap(node) for node in self._node.named_children]

    def child_by_field_name(self, name):
        return self._wrap(self._node.child_by_field_name(name))

    def __getattr__(self, name):
        return getattr(self._node, name)


def _tree_sitter(source, language, path, project_root, options):
    del path, project_root, options
    _, tree = parse(source, language)
    cache = {}
    root = NodeView(tree.root_node, cache)
    cache[root.id] = root
    # Preserve the existing fragment-tolerant tree-sitter contract.
    return ParsedDocument(root, ())


def _roslyn(source, language, path, project_root, options):
    from crapper.roslyn import parse_source

    del language
    document = compiler_document(parse_source(source, path, project_root, **dict(options)))
    errors = [item for item in document.diagnostics if item.severity.lower() == "error"]
    if errors:
        first = errors[0]
        raise SyntaxError(f"{path}: {first.code} {first.start_line}:{first.start_column}: {first.message}")
    return document


_PROVIDERS = {"csharp": _roslyn, "c_sharp": _roslyn}


@lru_cache(maxsize=64)
def _document(source, language, path, project_root, options):
    return _PROVIDERS.get(language, _tree_sitter)(source, language, path, project_root, options)


def parse_document(source, language, path, project_root=None, *, language_version=None,
                   symbols=None, configuration="Debug", target_framework=None):
    language = {"c_sharp": "csharp"}.get(language, language)
    options = (("language_version", language_version),
               ("symbols", None if symbols is None else tuple(symbols)),
               ("configuration", configuration), ("target_framework", target_framework))
    return _document(source, language, str(path), None if project_root is None else str(project_root), options)
