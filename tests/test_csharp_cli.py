from pathlib import Path

from crapper.cli import parse_args, run, select_files


def write(root: Path, path: str, text: str) -> Path:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def test_csharp_discovery_keeps_other_languages_in_dotnet_output_directories(tmp_path):
    source = write(tmp_path, "src/Widget.cs", "class Widget { int Get() => 1; }")
    other = write(tmp_path, "src/obj/script.py", "def example(): return 0")
    write(tmp_path, "src/obj/AssemblyInfo.cs", "class Generated {}")
    write(tmp_path, "src/Widget.g.cs", "class Generated {}")
    test = write(tmp_path, "Widget.Tests/WidgetTests.cs", "class WidgetTests { void Check() {} }")

    assert set(select_files(parse_args(["--root", str(tmp_path)]))) == {source, other}
    assert run(["--root", str(tmp_path), "--no-coverage", str(test)]) == 0
    assert ':name "Check"' in (tmp_path / ".metrics/crap.edn").read_text(encoding="utf-8")


def test_cli_scores_csharp_from_existing_lcov_branch_counts(tmp_path):
    write(tmp_path, "src/Widget.cs", "class Widget {\n int Get(bool ok) => ok ? 1 : 0;\n}\n")
    write(tmp_path, "coverage/lcov.info", "SF:src/Widget.cs\nDA:2,1\n"
          "BRDA:2,0,0,1\nBRDA:2,0,1,0\nend_of_record\n")

    assert run(["--root", str(tmp_path), "--use-existing-coverage"]) == 0
    snapshot = (tmp_path / ".metrics/crap.edn").read_text(encoding="utf-8")
    assert ':name "Get"' in snapshot
    assert ':coverage 50.0' in snapshot
    assert ':complexity 2' in snapshot
