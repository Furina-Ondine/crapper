from crapper.coverage import load_bundle
from crapper.model import Function
from crapper.runners import run_coverage
from crapper.cli import run
import pytest


def member(path="src/Box.cs", start=3, end=5):
    return Function("Choose", "Acme.Box", 2, start, end, path, "csharp")


def report(tmp_path, xml, location="target/coverage/csharp/run/coverage.cobertura.xml"):
    file = tmp_path / location
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(xml, encoding="utf-8")


def test_cobertura_uses_branch_hits_and_keeps_branchless_line_coverage(tmp_path):
    report(tmp_path, '''<coverage><sources><source>/checkout</source></sources><packages><package><classes>
    <class filename="src/Box.cs"><lines>
      <line number="3" hits="1" branch="true" condition-coverage="50% (1/2)"/>
      <line number="4" hits="1"/><line number="8" hits="0"/>
    </lines></class></classes></package></packages></coverage>''')
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(member()) == 50.0
    assert bundle.percent_for(member(start=4, end=8)) == 50.0
    assert bundle.percent_for(member("src/Missing.cs")) is None


def test_cobertura_merges_classes_and_reports_without_losing_covered_lines(tmp_path):
    first = '''<coverage><packages><package><classes>
    <class filename="src/Box.cs"><lines><line number="3" hits="1"/></lines></class>
    <class filename="src/Box.cs"><lines><line number="4" hits="1"/></lines></class>
    </classes></package></packages></coverage>'''
    report(tmp_path, first)
    report(tmp_path, '''<coverage><packages><package><classes>
    <class filename="src/Box.cs"><lines><line number="3" hits="0"/><line number="5" hits="1"/></lines></class>
    </classes></package></packages></coverage>''', "TestResults/other/coverage.cobertura.xml")
    bundle = load_bundle(tmp_path)
    assert bundle.percent_for(member()) == 100.0


def test_cobertura_handles_absolute_windows_paths_and_ignores_invalid_records(tmp_path):
    report(tmp_path, r'''<coverage><packages><package><classes>
    <class filename="D:\work\src\Box.cs"><lines>
    <line number="3" hits="2"/><line number="bad" hits="1"/>
    <line number="4" hits="bad"/><line number="5" hits="0"/>
    </lines></class></classes></package></packages></coverage>''')
    assert load_bundle(tmp_path).percent_for(member()) == 50.0


def test_cobertura_does_not_assign_an_ambiguous_basename_to_the_wrong_file(tmp_path):
    report(tmp_path, '''<coverage><packages><package><classes>
    <class filename="other/Box.cs"><lines><line number="3" hits="1"/></lines></class>
    </classes></package></packages></coverage>''')
    bundle = load_bundle(tmp_path)
    bundle.bind_sources(["src/Box.cs", "other/Box.cs"])
    assert bundle.percent_for(member()) is None


def test_default_vstest_coverage_runs_dotnet_and_removes_old_reports(tmp_path, monkeypatch):
    (tmp_path / "Demo.slnx").write_text("<Solution />", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    report(tmp_path, "<coverage/>")
    called = []
    def run(command, cwd):
        assert not list(tmp_path.glob("target/coverage/csharp/**/*.xml"))
        called.append((command, cwd))
        report(tmp_path, "<coverage/>")
        return 0
    monkeypatch.setattr("crapper.runners.run_shell", run)
    assert run_coverage(tmp_path, [source], None) == 0
    assert len(called) == 1
    assert called[0] == (["dotnet", "test", "--collect", "XPlat Code Coverage", "--results-directory", str(tmp_path / "target/coverage/csharp")], tmp_path.resolve())


def test_default_mtp_coverage_uses_its_native_collector(tmp_path, monkeypatch):
    (tmp_path / "global.json").write_text('{"test":{"runner":"Microsoft.Testing.Platform"}}', encoding="utf-8")
    (tmp_path / "Demo.sln").write_text("", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    called = []
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: called.append(command) or 0)
    run_coverage(tmp_path, [source], None)
    assert len(called) == 1
    command = called[0]
    assert command[:2] == ["dotnet", "test"]
    assert "--collect" not in command
    assert command[command.index("--coverage-output-format") + 1] == "cobertura"
    assert "--coverage" in command
    assert command[command.index("--results-directory-layout") + 1] == "per-module"


def test_default_coverage_warns_when_dotnet_emits_no_report(tmp_path, monkeypatch, capsys):
    (tmp_path / "Demo.csproj").write_text("<Project />", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    monkeypatch.setattr("crapper.runners.run_shell", lambda *args: 0)
    assert run_coverage(tmp_path, [source], None) == 1
    assert "No C# coverage report" in capsys.readouterr().err


def test_default_coverage_finds_projects_without_a_solution_and_skips_build_copies(tmp_path, monkeypatch):
    for relative in ("one/One.csproj", "two/Two.csproj", "one/obj/Copy.csproj", "two/bin/Copy.csproj"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<Project />", encoding="utf-8")
    source = tmp_path / "Box.cs"
    source.write_text("class Box {}", encoding="utf-8")
    called = []
    monkeypatch.setattr("crapper.runners.run_shell", lambda command, cwd: called.append((command, cwd)) or 0)
    run_coverage(tmp_path, [source], None)
    assert [cwd for _, cwd in called] == [tmp_path / "one", tmp_path / "two"]
    assert [cmd[cmd.index("--results-directory") + 1] for cmd, _ in called] == [str(tmp_path / "target/coverage/csharp/0"), str(tmp_path / "target/coverage/csharp/1")]


@pytest.mark.parametrize("text", ["", "<coverage>", "not xml"])
def test_invalid_cobertura_does_not_discard_other_coverage(tmp_path, text):
    report(tmp_path, text)
    report(tmp_path, '<coverage><packages><package><classes><class filename="src/Box.cs"><lines><line number="3" hits="1"/></lines></class></classes></package></packages></coverage>', "coverage/valid.cobertura.xml")
    assert load_bundle(tmp_path).percent_for(member()) == 100.0


def test_fresh_default_coverage_does_not_reuse_old_testresults(tmp_path, monkeypatch):
    source = tmp_path / "src/Box.cs"
    source.parent.mkdir()
    source.write_text("class Box {\n int Choose() {\n return 1;\n }\n}", encoding="utf-8")
    xml = '<coverage><packages><package><classes><class filename="src/Box.cs"><lines><line number="3" hits="1"/></lines></class></classes></package></packages></coverage>'
    report(tmp_path, xml, "TestResults/old/coverage.cobertura.xml")
    monkeypatch.setattr("crapper.cli.run_coverage", lambda *args: 0)
    assert run(["--root", str(tmp_path), "src/Box.cs"]) == 0
    metric = (tmp_path / ".metrics/crap.edn").read_text(encoding="utf-8")
    assert ":coverage 0.0" in metric
    assert (tmp_path / "TestResults/old/coverage.cobertura.xml").read_text(encoding="utf-8") == xml
    assert run(["--root", str(tmp_path), "--use-existing-coverage", "src/Box.cs"]) == 0
    assert ":coverage 100.0" in (tmp_path / ".metrics/crap.edn").read_text(encoding="utf-8")


def test_explicit_csharp_report_scope_does_not_import_stale_csharp_lcov(tmp_path):
    path = tmp_path / "target/coverage/lcov.info"
    path.parent.mkdir(parents=True)
    path.write_text("SF:src/Box.cs\nDA:3,1\nend_of_record\nSF:module.py\nDA:3,1\nend_of_record\n", encoding="utf-8")
    bundle = load_bundle(tmp_path, source_reports={"csharp": []})
    assert bundle.percent_for(member()) is None
    python = Function("choose", "module", 1, 3, 3, "module.py", "python")
    assert bundle.percent_for(python) == 100.0


def test_report_scope_is_shared_by_languages_and_accepts_explicit_lcov(tmp_path):
    old = tmp_path / "target/coverage/lcov.info"
    old.parent.mkdir(parents=True)
    old.write_text("SF:module.py\nDA:3,1\nend_of_record\nSF:other.py\nDA:3,1\nend_of_record\n", encoding="utf-8")
    current = tmp_path / "current.info"
    current.write_text("SF:module.py\nDA:3,0\nend_of_record\n", encoding="utf-8")
    bundle = load_bundle(tmp_path, source_reports={"python": [current]})
    assert bundle.percent_for(Function("choose", "module", 1, 3, 3, "module.py", "python")) == 0.0
    assert bundle.percent_for(Function("choose", "other", 1, 3, 3, "other.py", "python")) is None
@pytest.mark.parametrize("filename,expected", [
    ("src/A.cs", "/workspace/src/A.cs"),
    ("/actual/A.cs", "/actual/A.cs"),
    ("C:/actual/A.cs", "C:/actual/A.cs"),
    ("", None),
])
def test_cobertura_source_root_only_prefixes_nonempty_relative_paths(filename, expected):
    from crapper.coverage import parse_cobertura

    result = parse_cobertura(f'<coverage><sources><source>/workspace</source></sources><packages><package><classes><class filename="{filename}"><lines><line number="7" hits="1"/></lines></class></classes></package></packages></coverage>')
    assert set(result) == ({expected} if expected else set())


def test_cobertura_missing_or_blank_source_elements_do_not_change_relative_ownership():
    from crapper.coverage import parse_cobertura

    result = parse_cobertura('<coverage><sources><source/><source>  </source></sources><packages><package><classes><class filename="src/A.cs"><lines><line number="7" hits="0"/></lines></class></classes></package></packages></coverage>')
    assert set(result) == {"src/A.cs"}
    assert result["src/A.cs"] == {7: (0, 1)}


def test_failed_collector_report_is_rejected_even_when_xml_was_written(tmp_path, monkeypatch, capsys):
    (tmp_path / "Demo.slnx").write_text("<Solution />")
    def collector(command, directory):
        report(tmp_path, '<coverage/>')
        return 1

    monkeypatch.setattr("crapper.runners.run_shell", collector)
    assert run_coverage(tmp_path, [tmp_path / "A.cs"], None) == 1
    assert "C# coverage exited 1" in capsys.readouterr().err


def test_custom_collector_exit_one_warns_about_stale_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("crapper.runners.run_shell", lambda *args: 1)
    assert run_coverage(tmp_path, [tmp_path / "A.cs"], "collector") == 1
    assert "Reports already on disk will not be read" in capsys.readouterr().err
