import pytest

from crapper.languages import functions_in_file
from crapper.languages.csharp import units_in_source


def read(source):
    return functions_in_file("csharp", source, "src/Box.cs", ".")


def test_csharp_executable_members_keep_namespace_complexity_and_spans():
    source = """namespace Acme;
public class Box {
    string title = "雪";
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
        ("Acme.Box", "Box", 1),
        ("Acme.Box", "~Box", 1),
        ("Acme.Box", "Choose", 2),
        ("Acme.Box", "Value.get", 1),
        ("Acme.Box", "Value.set", 2),
        ("Acme.Box", "Twice.get", 1),
        ("Acme.Box", "this.get", 1),
        ("Acme.Box.Inner", "Run", 1),
    ]
    choose = found[2]
    assert (choose.start_line, choose.end_line) == (6, 6)
    assert source.encode("utf-8")[choose.start_byte:choose.end_byte].decode() == (
        "public int Choose(int x) => x > 0 ? 1 : 0;"
    )
    assert found[3].end_byte <= found[4].start_byte


def test_csharp_top_level_owns_local_functions_and_lambdas_once():
    source = """using System;
int Local(int x) => x > 0 ? 1 : 0;
Func<bool, int> f = ready => ready ? Local(1) : 0;
if (f(true) > 0) Console.WriteLine(f(false));
namespace Demo {
    class Box {
        int Choose(int? x, bool ready) {
            try {
                x ??= ready && x is > 0 and < 8 ? 1 : 2;
                return (x ?? 0) switch { 1 => 1, > 2 when ready => 2, _ => 3 };
            } catch (Exception) when (ready) { return 0; }
        }
    }
}
"""
    found = read(source)
    assert [(f.namespace, f.name, f.complexity) for f in found] == [
        ("Program", "<top-level>", 4),
        ("Demo.Box", "Choose", 11),
    ]
    top_level = found[0]
    assert (top_level.start_line, top_level.end_line) == (2, 4)


def test_csharp_operators_explicit_members_and_event_accessors():
    source = """struct S {
    public static S operator +(S a, S b) => a;
    public static implicit operator int(S a) => 1;
    int IThing.Read() => 1;
    int IThing.Value => 1;
    int IThing.this[int i] { get => i; }
    event System.Action Changed { add { } remove { } }
    int Switch(int x) {
        switch (x) {
            case 1: case 2: return 1;
            case > 2 when x < 10: return 2;
            default: return 0;
        }
    }
}"""
    found = read(source)
    assert [(f.name, f.complexity) for f in found] == [
        ("operator +", 1),
        ("implicit operator int", 1),
        ("IThing.Read", 1),
        ("IThing.Value.get", 1),
        ("IThing.this.get", 1),
        ("Changed.add", 1),
        ("Changed.remove", 1),
        ("Switch", 5),
    ]


def test_csharp_syntax_recovery_does_not_publish_misparsed_units():
    source = """class C {
    int value;
    ref int At<T>(int index) => ref value;
    void Set(bool flag, int index) {
        At<int>(flag ? index : 0) = flag ? 1 : 2;
        if (flag) At<int>(index) = 3;
    }
    void Neighbor() { }
}"""
    with pytest.raises(SyntaxError, match=r"src/Box\.cs:\d+:\d+: .*C#"):
        read(source)


def test_csharp_executable_units_expose_original_syntax_and_member_visibility():
    source = """class C {
    int Hidden() { int Local(bool b) => b ? 1 : 0; return Local(true); }
    public int Value { get => 1; private set { } }
}
interface I { int Default() => 1; }
"""
    data, found = units_in_source(source, "src/Box.cs")
    assert [unit.function for unit in found] == read(source)
    assert [(u.function.name, u.function.complexity, u.private) for u in found] == [
        ("Hidden", 2, True),
        ("Value.get", 1, False),
        ("Value.set", 1, True),
        ("Default", 1, False),
    ]
    for unit in found:
        node, = unit.nodes
        assert node.text == data[unit.function.start_byte:unit.function.end_byte]


def test_csharp_top_level_counts_both_source_branches_of_a_directive():
    source = """#if FEATURE
if (ready) Run();
#else
void Local(bool ready) { if (ready) Run(); }
#endif
class C { void Other() {} }
"""
    assert [(f.name, f.complexity) for f in read(source)] == [
        ("<top-level>", 3),
        ("Other", 1),
    ]
