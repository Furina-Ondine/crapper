"""Exercise the real JSON-lines executable without importing the Python bridge.

Run: python protocol_test.py path/to/RoslynHost.dll
"""

import json
from pathlib import Path
import subprocess
import sys
import unittest

HOST = str(Path(sys.argv[1]).resolve())


def documents(*requests):
    result = subprocess.run(
        ["dotnet", HOST],
        input="".join(json.dumps({"path": "sample.cs", "source": source, **options}, ensure_ascii=False) + "\n" for source, options in requests),
        text=True, encoding="utf-8", capture_output=True, check=True,
    )
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    if len(responses) != len(requests):
        raise AssertionError((len(responses), len(requests), result.stderr))
    return responses


def parse(source, **options):
    return documents((source, options))[0]


def descendants(document, ids):
    stack = list(reversed(ids))
    while stack:
        node = document["nodes"][stack.pop()]
        yield node
        stack.extend(reversed(node["children"]))


class ProtocolTests(unittest.TestCase):
    def test_file_based_program_is_an_explicit_compiler_context(self):
        source = '#:property TargetFramework=net10.0\nSystem.Console.WriteLine(1);'
        project, loose = documents((source, {}), (source, {"fileBasedProgram": True}))
        self.assertIn("CS9298", [item["code"] for item in project["diagnostics"]])
        self.assertFalse([item for item in loose["diagnostics"] if item["severity"] == "error"])
        self.assertEqual([(unit["namespace"], unit["name"]) for unit in loose["units"]],
                         [("Program", "<top-level>")])

    def test_batch_parses_ref_return_assignments_and_preserves_utf8_coordinates(self):
        source = '// 😀中文\r\nclass C { int F(int 值) => 值 > 0 ? 1 : 0; }\r\n'
        ref_return = 'class C { void F(ref int a, ref int b) { Unsafe.Add(ref a, 1) = Unsafe.Add(ref b, 0); } }'
        first, second = documents((source, {}), (ref_return, {}))
        self.assertFalse([d for d in first["diagnostics"] if d["severity"] == "error"])
        self.assertFalse([d for d in second["diagnostics"] if d["severity"] == "error"])
        unit = first["units"][0]
        self.assertEqual((unit["name"], unit["namespace"], unit["line"], unit["endLine"]), ("F", "C", 2, 2))
        self.assertEqual(source.encode()[unit["start"]:unit["end"]].decode(), "int F(int 值) => 值 > 0 ? 1 : 0;")
        operator = next(node for node in first["nodes"] if source.encode()[node["start"]:node["end"]] == b">" and "operator" in node["roles"])
        self.assertEqual((operator["startLine"], operator["startColumn"]), (2, len('class C { int F(int 值) => 值 '.encode())))

    def test_members_share_names_and_visibility(self):
        source = '''namespace A.B;
class C {
 public C() {} ~C() {}
 private int Hidden() => 1;
 public int Property { get => 1; private set {} }
 int I.Value => 1;
 int I.this[int i] => i;
 event System.Action Changed { add {} remove {} }
 public static C operator +(C a, C b) => a;
 public static implicit operator int(C a) => 1;
 class Inner { public void Run() {} }
 public int Automatic { get; set; }
}'''
        document = parse(source)
        self.assertEqual([unit["name"] for unit in document["units"]], ["C", "~C", "Hidden", "Property.get", "Property.set", "I.Value.get", "I.this.get", "Changed.add", "Changed.remove", "operator +", "implicit operator int", "Run"])
        self.assertEqual(document["units"][-1]["namespace"], "A.B.C.Inner")
        values = {unit["name"]: unit["private"] for unit in document["units"]}
        self.assertFalse(values["C"])
        self.assertTrue(values["Hidden"])
        self.assertFalse(values["Property.get"])
        self.assertTrue(values["Property.set"])
        self.assertTrue(values["I.Value.get"])

    def test_top_level_units_own_all_global_statements_and_local_functions(self):
        source = 'var x = 1;\nif (x > 0) Local(x);\nint Local(int n) => n > 0 ? 1 : 0;\nclass C { void Run() {} }'
        document = parse(source)
        self.assertEqual([(u["namespace"], u["name"]) for u in document["units"]], [("Program", "<top-level>"), ("C", "Run")])
        top = document["units"][0]
        self.assertFalse(top["private"])
        self.assertEqual(len(top["syntax"]), 3)
        self.assertEqual((top["line"], top["endLine"]), (1, 3))
        self.assertEqual(sum("decision" in n["roles"] for n in descendants(document, top["syntax"])), 2)

    def test_decisions_use_syntax_and_default_arms_do_not_add_choices(self):
        source = '''class C { int F(int? x, bool ready) {
if (ready && x != null || x is > 0 and < 10) return 1;
for (;;) { break; } foreach (var i in new[] { 1 }) {}
while (ready) { break; } do {} while (ready);
try {} catch (Exception) {} var y = x ?? 0;
return y switch { 0 => 1, > 1 when ready => 2, _ => 3 };
} }'''
        document = parse(source)
        self.assertEqual(sum("decision" in n["roles"] for n in descendants(document, document["units"][0]["syntax"])), 13)
        switch = parse('class C { int F(int x) { switch (x) { case 1: case 2: return 1; case > 2 when x < 10: return 2; default: return 0; } } }')
        self.assertEqual(sum("decision" in n["roles"] for n in switch["nodes"]), 4)

    def test_native_kinds_roles_and_tree_ids_are_consistent(self):
        source = 'class C { [A(1)] bool F(int x) => !(x > 0) && true; object G() => new Box<int>(1); string H(int x) => $"text {x + 1}"; }'
        document = parse(source)
        self.assertEqual(document["root"], 0)
        self.assertEqual(document["nodes"][0]["kind"], "CompilationUnit")
        parents = {}
        for index, node in enumerate(document["nodes"]):
            for child in node["children"]:
                self.assertGreater(child, index)
                self.assertNotIn(child, parents)
                parents[child] = index
            self.assertLessEqual(node["start"], node["end"])
            self.assertLessEqual(node["end"], len(source.encode()))
        self.assertEqual(set(parents), set(range(1, len(document["nodes"]))))
        roles = {role for node in document["nodes"] for role in node["roles"]}
        self.assertTrue({"literal", "number", "boolean", "operator", "binary", "unary", "group", "call", "metadata", "type_scope", "type_arguments", "arguments"}.issubset(roles))
        self.assertTrue(all(not node["named"] for node in document["nodes"] if {"number", "boolean"}.intersection(node["roles"])))
        self.assertEqual(sum("number" in node["roles"] for node in document["nodes"]), 4)

    def test_preprocessor_symbols_and_language_version_are_real_parse_options(self):
        source = '#if ACTIVE\nclass Active { void F() {} }\n#else\nclass Inactive { void G() {} }\n#endif\n'
        active = parse(source, symbols=["ACTIVE"], languageVersion="latest")
        inactive = parse(source, symbols=[])
        self.assertEqual(active["units"][0]["namespace"], "Active")
        self.assertEqual(inactive["units"][0]["namespace"], "Inactive")
        field = 'class C { int Property { get => field; set { field = value; } } }'
        old = parse(field, languageVersion="13")
        current = parse(field, languageVersion="14")
        self.assertEqual(old["languageVersion"], "13.0")
        self.assertNotIn("FieldExpression", {node["kind"] for node in old["nodes"]})
        self.assertIn("FieldExpression", {node["kind"] for node in current["nodes"]})

    def test_callee_roles_do_not_hide_initializers_or_postfix_suppression(self):
        source = 'class C { object F(int x) => new Box<int>(Read(x)) { Value = x + 1 }; string G(string x) => x!; }'
        document = parse(source)
        creation = next(node for node in document["nodes"] if node["kind"] == "ObjectCreationExpression")
        children = [document["nodes"][index] for index in creation["children"]]
        self.assertEqual([source.encode()[node["start"]:node["end"]].decode() for node in children if "callee" in node["roles"]], ["Box<int>"])
        self.assertIn("ObjectInitializerExpression", {node["kind"] for node in children})
        initializer = next(node for node in children if node["kind"] == "ObjectInitializerExpression")
        self.assertTrue(any(node["kind"] == "AddExpression" for node in descendants(document, initializer["children"])))
        suppression = next(node for node in document["nodes"] if node["kind"] == "SuppressNullableWarningExpression")
        self.assertNotIn("unary", suppression["roles"])

    def test_invalid_transport_or_language_version_fails_explicitly(self):
        for request in ('not json\n', 'null\n', json.dumps({"path": "sample.cs", "source": "class C {}", "languageVersion": "not-a-version"}) + '\n'):
            result = subprocess.run(["dotnet", HOST], input=request, text=True, encoding="utf-8", capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(result.stdout)
            self.assertTrue(result.stderr.strip())

    def test_true_false_operator_declarations_are_not_boolean_literals(self):
        source = 'struct Flag { public static bool operator true(Flag value) => true; public static bool operator false(Flag value) => false; }'
        document = parse(source)
        booleans = [node for node in document["nodes"] if "boolean" in node["roles"]]
        self.assertEqual(len(booleans), 2)
        self.assertEqual([source.encode()[node["start"]:node["end"]].decode() for node in booleans], ["true", "false"])
        self.assertEqual([unit["name"] for unit in document["units"]], ["operator true", "operator false"])

    def test_interface_default_and_explicit_visibility_share_the_member_contract(self):
        document = parse('interface I { void Default() {} private void Hide() {} protected void Protected() {} internal void Internal() {} }')
        self.assertEqual({unit["name"]: unit["private"] for unit in document["units"]}, {"Default": False, "Hide": True, "Protected": False, "Internal": False})
        members = parse('class C { void Hide() {} protected void Protected() {} internal void Internal() {} }')
        self.assertEqual({unit["name"]: unit["private"] for unit in members["units"]}, {"Hide": True, "Protected": False, "Internal": False})

    def test_syntax_errors_are_returned_with_original_source_spans(self):
        source = 'class C { int F( {'
        document = parse(source)
        errors = [diagnostic for diagnostic in document["diagnostics"] if diagnostic["severity"] == "error"]
        self.assertTrue(errors)
        for error in errors:
            self.assertTrue(error["code"].startswith("CS"))
            self.assertTrue(error["message"])
            self.assertEqual(error["line"], 1)
            self.assertGreaterEqual(error["column"], 0)
            self.assertLessEqual(0, error["start"])
            self.assertLessEqual(error["start"], error["end"])
            self.assertLessEqual(error["end"], len(source.encode()))

    def test_literal_roles_are_on_tokens_and_invocation_callee_is_exact(self):
        source = 'class C { string F(int x) => $"text {Read(x + 1)}"; }'
        document = parse(source)
        for node in document["nodes"]:
            if node["kind"] in {"NumericLiteralToken", "InterpolatedStringTextToken"}:
                self.assertIn("literal", node["roles"])
        invocation = next(n for n in document["nodes"] if n["kind"] == "InvocationExpression")
        children = [document["nodes"][i] for i in invocation["children"]]
        self.assertEqual([source.encode()[n["start"]:n["end"]].decode() for n in children if "callee" in n["roles"]], ["Read"])
        self.assertTrue(all("callee" not in node["roles"] for node in document["nodes"] if node["kind"] == "ClassDeclaration"))

    def test_physical_member_end_lines_with_flush_left_and_missing_delimiters(self):
        source = 'class C {\nvoid F() {\n}\n}'
        self.assertEqual(parse(source)["units"][0]["endLine"], 3)
        incomplete = 'class C {\nvoid F() {\n'
        document = parse(incomplete)
        self.assertTrue(document["diagnostics"])
        self.assertEqual(document["units"][0]["endLine"], 2)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
