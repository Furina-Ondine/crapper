"""Behavior of the shared syntax boundary, using the real compiler frontend."""

import pytest

from crapper.frontend import parse_document


def walk(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.children))


def test_roslyn_accepts_ref_return_assignment_and_keeps_native_syntax():
    document = parse_document(
        "class C { void Copy() { Unsafe.Add(ref a, 1) = Unsafe.Add(ref b, 0); } }",
        "csharp", "Copy.cs",
    )
    assert not document.diagnostics
    assert [unit.name for unit in document.units] == ["Copy"]
    calls = [node for node in walk(document.root) if "call" in node.roles]
    assert len(calls) == 2
    assert {node.kind for node in calls} == {"InvocationExpression"}
    assert all(node.parent is not None for node in calls)


def test_utf8_spans_and_physical_lines_survive_emoji_and_crlf():
    source = '// 中文😀\r\nclass C { int 一() => 1; int 二() => 0; }\r\n'
    document = parse_document(source, "csharp", "Unicode.cs")
    data = source.encode("utf-8")
    assert [data[u.start_byte:u.end_byte].decode() for u in document.units] == [
        "int 一() => 1;", "int 二() => 0;",
    ]
    numbers = [node for node in walk(document.root) if "number" in node.roles]
    assert [data[n.start_byte:n.end_byte] for n in numbers] == [b"1", b"0"]
    assert all(n.start_point[0] == 1 for n in numbers)
    assert all(n.start_point[1] == n.start_byte - data.index(b"class") for n in numbers)


def test_invalid_csharp_fails_with_path_and_compiler_location():
    with pytest.raises(SyntaxError, match=r"Broken.cs.*CS\d+.*2:"):
        parse_document("class C {\n int F( => 1; }", "csharp", "Broken.cs")


def test_compiler_options_select_active_code_and_are_part_of_cache_key():
    source = '#if ACTIVE\nclass On { int F() => 1; }\n#else\nclass Off { int F() => 0; }\n#endif'
    on = parse_document(source, "csharp", "Conditional.cs", symbols=("ACTIVE",), language_version="12.0")
    off = parse_document(source, "csharp", "Conditional.cs", symbols=(), language_version="12.0")
    assert [u.namespace for u in on.units] == ["On"]
    assert [u.namespace for u in off.units] == ["Off"]
    assert on.language_version == "12.0"
    assert parse_document(source, "csharp", "Conditional.cs", symbols=("ACTIVE",), language_version="12.0") is on


def test_tree_sitter_provider_preserves_fields_roles_and_node_identity():
    document = parse_document("def f(x):\n return x + 1\n", "python", "sample.py")
    binary = next(n for n in walk(document.root) if "binary" in n.roles)
    assert binary.type == "binary_operator"
    assert binary.child_by_field_name("left") is binary.children[0]
    assert binary.children[0].parent is binary
    assert any("number" in n.roles for n in binary.children)


def test_project_context_uses_custom_and_framework_symbols(tmp_path):
    (tmp_path / "App.csproj").write_text('''<Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><TargetFramework>net10.0</TargetFramework><LangVersion>12.0</LangVersion>
      <DefineConstants>$(DefineConstants);CUSTOM</DefineConstants></PropertyGroup>
    </Project>''', encoding="utf-8")
    source = '#if CUSTOM && NET10_0\nclass Selected { int F() => 1; }\n#else\nclass Wrong { int F() => 0; }\n#endif'
    document = parse_document(source, "csharp", str(tmp_path / "Sample.cs"), project_root=str(tmp_path))
    assert [u.namespace for u in document.units] == ["Selected"]
    assert document.language_version == "12.0"


def test_bad_options_do_not_poison_the_shared_host():
    with pytest.raises(RuntimeError, match="version"):
        parse_document("class C {}", "csharp", "Options.cs", language_version="unknown-version")
    document = parse_document("class Recovered { int F() => 1; }", "csharp", "Options.cs")
    assert [u.namespace for u in document.units] == ["Recovered"]


def test_csharp_alias_shares_the_same_cached_document():
    source = "class Alias { void F() {} }"
    assert parse_document(source, "csharp", "Alias.cs") is parse_document(source, "c_sharp", "Alias.cs")


def test_first_use_builds_only_in_temporary_cache(tmp_path, monkeypatch):
    import tempfile
    from crapper import roslyn

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    # A cache parent may already belong to an older host/compiler version.
    (tmp_path / "ub-mode/roslyn").mkdir(parents=True)
    roslyn._build.cache_clear()
    document = parse_document("class ColdStart { int F() => 1; }", "csharp", "ColdStart.cs")
    assert document.units[0].namespace == "ColdStart"
    assert len(list(tmp_path.rglob("RoslynHost.dll"))) == 1
    assert not list(tmp_path.rglob("*.csproj"))


def test_one_syntax_diagnostic_raises_syntax_error():
    from crapper.roslyn import parse_source

    source = 'class C {}\n}'
    diagnostics = parse_source(source, 'SingleDiagnostic.cs')['diagnostics']
    assert len([d for d in diagnostics if d['severity'].lower() == 'error']) == 1
    with pytest.raises(SyntaxError, match=r'SingleDiagnostic.cs.*CS1022.*2:'):
        parse_document(source, 'csharp', 'SingleDiagnostic.cs')


def test_warning_and_node_end_coordinates_are_preserved():
    source = '#warning hello\r\nclass C {\r\n  int F() => 1;\r\n}\r\n'
    document = parse_document(source, 'csharp', 'Warning.cs')
    warning, = document.diagnostics
    assert warning.code == 'CS1030'
    assert warning.severity.lower() == 'warning'
    method = next(node for node in document.nodes if node.kind == 'MethodDeclaration')
    assert method.start_point == (2, 2)
    assert method.end_point == (2, len('  int F() => 1;'))
    assert method.child_count == len(method.children)
    assert method.named_children == [child for child in method.children if child.is_named]
    assert method.child_by_field_name('anything') is None


def test_project_multitarget_and_explicit_options(tmp_path):
    (tmp_path / 'App.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk">
      <PropertyGroup><TargetFrameworks>net8.0;net10.0</TargetFrameworks>
      <LangVersion>12.0</LangVersion><DefineConstants>PROJECT</DefineConstants></PropertyGroup>
    </Project>''', encoding='utf-8')
    source = '#if PROJECT && NET10_0\nclass Selected { int F() => 1; }\n#else\nclass Wrong { int F() => 0; }\n#endif'
    path = str(tmp_path / 'Multi.cs')
    selected = parse_document(source, 'csharp', path, project_root=str(tmp_path), target_framework='net10.0')
    assert [u.namespace for u in selected.units] == ['Selected']
    assert selected.language_version == '12.0'
    overridden = parse_document(source, 'csharp', path, project_root=str(tmp_path), target_framework='net10.0', symbols=())
    assert [u.namespace for u in overridden.units] == ['Wrong']
    assert overridden.language_version == '12.0'
    first_source = '#if PROJECT && NET8_0\nclass First { int F() => 1; }\n#else\nclass Wrong { int F() => 0; }\n#endif'
    first = parse_document(first_source, 'csharp', path, project_root=str(tmp_path))
    assert [u.namespace for u in first.units] == ['First']
    explicit_version = parse_document(first_source, 'csharp', path, project_root=str(tmp_path), language_version='13.0')
    assert [u.namespace for u in explicit_version.units] == ['First']
    assert explicit_version.language_version == '13.0'


def test_relative_source_stops_project_search_at_root(tmp_path):
    (tmp_path / 'Parent.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <TargetFramework>net10.0</TargetFramework><DefineConstants>OUTSIDE</DefineConstants>
      </PropertyGroup></Project>''', encoding='utf-8')
    root = tmp_path / 'nested'
    root.mkdir()
    source = '#if OUTSIDE\nclass Wrong { int F() => 0; }\n#else\nclass Selected { int F() => 1; }\n#endif'
    document = parse_document(source, 'csharp', 'Sample.cs', project_root=str(root))
    assert [u.namespace for u in document.units] == ['Selected']


def test_relative_source_uses_the_supplied_project_context(tmp_path):
    (tmp_path / 'App.csproj').write_text("""<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
      <TargetFramework>net10.0</TargetFramework><DefineConstants>LOCAL_PROJECT</DefineConstants>
      </PropertyGroup></Project>""", encoding='utf-8')
    source = '#if LOCAL_PROJECT\nclass Selected { int Run() => 1; }\n#else\nclass Wrong { int Run() => 0; }\n#endif'
    document = parse_document(source, 'csharp', 'Relative.cs', project_root=str(tmp_path))
    assert [unit.namespace for unit in document.units] == ['Selected']


def test_file_based_program_directives_use_the_compiler_context(tmp_path):
    source = '#:property TargetFramework=net10.0\nSystem.Console.WriteLine(1);'
    loose = tmp_path / 'loose'
    loose.mkdir()
    document = parse_document(source, 'csharp', str(loose / 'Program.cs'), project_root=str(loose))
    assert [(unit.namespace, unit.name) for unit in document.units] == [('Program', '<top-level>')]
    (loose / 'App.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup></Project>', encoding='utf-8')
    # Different path avoids reusing the first context snapshot after adding a project.
    with pytest.raises(SyntaxError, match='CS9298'):
        parse_document(source, 'csharp', str(loose / 'ProjectSource.cs'), project_root=str(loose))
