from crapper.discover import is_test_file, iter_source_files, language_of
from crapper.cli import run
import pytest
from crapper.languages import functions_in_file


def read(source):
    return functions_in_file("csharp", source, "src/Box.cs", "/proj")


def test_csharp_members_keep_namespace_type_and_executable_spans():
    source = """namespace Acme.Tools;
public class Box {
    public Box() { }
    ~Box() { }
    public int Choose(int x) => x > 0 ? 1 : 0;
    public int Value { get => 1; set { if (value > 0) { } } }
    public int Twice => Value * 2;
    public int this[int i] => i;
    public int Automatic { get; set; }
    public abstract class Inner { public abstract void Skip(); public void Run() {} }
}
"""
    found = read(source)
    assert [(f.namespace, f.name, f.complexity) for f in found] == [
        ("Acme.Tools.Box", "Box", 1), ("Acme.Tools.Box", "~Box", 1),
        ("Acme.Tools.Box", "Choose", 2), ("Acme.Tools.Box", "Value.get", 1),
        ("Acme.Tools.Box", "Value.set", 2), ("Acme.Tools.Box", "Twice.get", 1),
        ("Acme.Tools.Box", "this.get", 1), ("Acme.Tools.Box.Inner", "Run", 1),
    ]
    assert all(f.language == "csharp" and 0 <= f.start_byte < f.end_byte for f in found)
    choose = found[2]
    assert (choose.start_line, choose.end_line) == (5, 5)
    assert source.encode()[choose.start_byte:choose.end_byte].decode().startswith("public int Choose")


def test_counts_csharp_decisions_including_patterns_and_null_coalescing():
    source = """namespace A { namespace B {
record R {
 int F(int? x, bool ready) {
   if (ready && x != null || x is > 0 and < 10) return 1;
   for (;;) { break; }
   foreach (var i in new[] { 1 }) { }
   while (ready) { break; }
   do {} while (ready);
   try {} catch (Exception) { }
   var y = x ?? 0;
   return y switch { 0 => 1, > 1 when ready => 2, _ => 3 };
 }
}}}
"""
    found = read(source)
    assert [(f.namespace, f.name, f.complexity) for f in found] == [("A.B.R", "F", 14)]


def test_local_functions_and_lambdas_belong_to_outer_member():
    found = read('class C { int Outer() { int Local(int x) => x > 0 ? 1 : 0; System.Func<bool, int> f = b => b ? 1 : 0; return Local(1); } }')
    assert [(f.name, f.complexity) for f in found] == [("Outer", 3)]


def test_switch_statement_counts_case_labels_and_guards_but_not_default():
    found = read('class C { int F(int x) { switch (x) { case 1: case 2: return 1; case > 2 when x < 10: return 2; default: return 0; } } }')
    assert [(f.name, f.complexity) for f in found] == [("F", 5)]


def test_operators_explicit_members_and_event_accessors():
    found = read('''struct S {
 public static S operator +(S a, S b) => a;
 public static implicit operator int(S a) => 1;
 int IThing.Read() => 1;
 event System.Action Changed { add { } remove { } }
}''')
    assert [f.name for f in found] == ["operator +", "implicit operator int", "IThing.Read", "Changed.add", "Changed.remove"]


def test_discovers_csharp_and_ignores_compiled_generated_directories(tmp_path):
    for relative in ("src/Box.cs", "src/obj/Generated.cs", "bin/Output.cs", "TestResults/Copy.cs", ".artifacts/Copy.cs", ".vs/Copy.cs", "BenchmarkDotNet.Artifacts/Copy.cs", "src/View.g.cs", "src/View.Designer.cs"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("class C {}", encoding="utf-8")
    assert language_of("Box.cs") == "csharp"
    assert [p.relative_to(tmp_path).as_posix() for p in iter_source_files([tmp_path])] == ["src/Box.cs"]


def test_top_level_program_owns_statements_and_local_functions():
    source = 'using System;\nvar x = 1;\nif (x > 0) Console.WriteLine(Local(x));\nint Local(int n) => n > 1 ? 1 : 0;\nclass Other { public void Run() {} }'
    found = read(source)
    assert [(f.namespace, f.name, f.complexity) for f in found] == [("Program", "<top-level>", 3), ("Other", "Run", 1)]
    top = found[0]
    assert (top.start_line, top.end_line) == (2, 4)
    assert source.encode()[top.start_byte:top.end_byte].decode().startswith("var x = 1;")
    assert source.encode()[top.start_byte:top.end_byte].decode().endswith("int Local(int n) => n > 1 ? 1 : 0;")


def test_explicit_interface_properties_and_indexers_keep_the_interface_name():
    found = read('class C : I { int I.Value => 1; int I.this[int i] => i; int I.Writable { get => 1; set {} } }')
    assert [f.name for f in found] == ["I.Value.get", "I.this.get", "I.Writable.get", "I.Writable.set"]


@pytest.mark.parametrize("path", ["App.Tests/Case.cs", "App.Test/Case.cs", "app.tests/Case.cs", "CaseTests.cs", "CaseTest.cs", "case_tests.cs"])
def test_csharp_test_conventions_are_skipped_by_default_but_explicit_files_are_included(tmp_path, path):
    file = tmp_path / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("class Case { public int Run() => 1; }", encoding="utf-8")
    assert is_test_file(path)
    assert iter_source_files([tmp_path]) == []
    assert run(["--root", str(tmp_path), "--no-coverage", path]) == 0
    assert ':name "Run"' in (tmp_path / ".metrics/crap.edn").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", ["Contest/Case.cs", "Latest.TestsData/Case.cs", "Contest.cs", "Latest.cs", "src/Box.cs"])
def test_similar_production_names_remain_source(path):
    assert not is_test_file(path)


def test_extracted_members_carry_visibility_for_all_consumers():
    source = '''class C {
 int Hidden() => 1;
 public int Value { get => 1; private set {} }
 internal int Shared() => 1;
}
interface I { int Default() => 1; }
'''
    assert {(fn.namespace, fn.name): fn.private for fn in read(source)} == {
        ("C", "Hidden"): True,
        ("C", "Value.get"): False,
        ("C", "Value.set"): True,
        ("C", "Shared"): False,
        ("I", "Default"): False,
    }


def test_invalid_csharp_cli_returns_error_without_writing_partial_metrics(tmp_path, capsys):
    (tmp_path / "Broken.cs").write_text("class C { int F( => 1; }", encoding="utf-8")
    assert run(["--root", str(tmp_path), "--no-coverage"]) == 1
    assert "CS" in capsys.readouterr().err
    assert not (tmp_path / ".metrics/crap.edn").exists()
