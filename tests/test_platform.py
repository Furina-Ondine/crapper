"""Exercise the CLI and runners through real OS process boundaries."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from crapper.languages.treesitter import parser_for
from crapper.runners import _python_executable, run_shell


def test_help_writes_utf8_when_the_default_output_codec_is_gbk():
    result = subprocess.run(
        [sys.executable, "-m", "crapper", "--help"],
        env={**os.environ, "PYTHONIOENCODING": "gbk"},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CC² × (1 − coverage)³" in result.stdout.decode("utf-8")


def test_report_preserves_unicode_in_a_redirected_stream(tmp_path):
    (tmp_path / "demo.clj").write_text(
        "(ns 演示.核心)\n(defn 选择😀 [x] (if x 1 0))\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-m", "crapper", "--root", str(tmp_path), "--no-coverage"],
        env={**os.environ, "PYTHONIOENCODING": "gbk"},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "选择😀" in result.stdout.decode("utf-8")
    assert "选择😀" in (tmp_path / ".metrics" / "crap.edn").read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows project interpreter")
def test_python_coverage_uses_a_windows_project_venv(tmp_path):
    binary = tmp_path / ".venv" / "Scripts" / "python.exe"
    binary.parent.mkdir(parents=True)
    binary.touch()
    assert _python_executable(tmp_path) == str(binary)


def test_python_coverage_falls_back_to_the_running_interpreter(tmp_path):
    assert _python_executable(tmp_path) == sys.executable


def test_python_coverage_ignores_another_platforms_venv(tmp_path):
    other_executable = "bin/python" if os.name == "nt" else "Scripts/python.exe"
    binary = tmp_path / ".venv" / other_executable
    binary.parent.mkdir(parents=True)
    binary.touch()
    assert _python_executable(tmp_path) == sys.executable


@pytest.mark.parametrize("has_download", [False, True])
def test_parser_supports_bundled_and_downloadable_language_packs(monkeypatch, has_download):
    calls = []
    parser = object()
    pack = SimpleNamespace(get_parser=lambda language: parser)
    if has_download:
        pack.download = lambda languages: calls.extend(languages)
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", pack)
    parser_for.cache_clear()
    try:
        assert parser_for("python") is parser
        assert calls == (["python"] if has_download else [])
    finally:
        parser_for.cache_clear()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch executable lookup")
def test_coverage_finds_cmd_tools_on_path(tmp_path, monkeypatch):
    scripts = tmp_path / "tool scripts"
    scripts.mkdir()
    (scripts / "coverage-tool.cmd").write_text("@exit /b 7\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(scripts) + os.pathsep + os.environ.get("PATH", ""))
    assert run_shell(["coverage-tool"], tmp_path) == 7


@pytest.mark.skipif(sys.platform != "win32", reason="Windows batch arguments")
def test_coverage_batch_tool_receives_literal_arguments(tmp_path, monkeypatch):
    capture = tmp_path / "capture.py"
    capture.write_text(
        "import json, pathlib, sys\n"
        "pathlib.Path('arguments.json').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    tool = tmp_path / "coverage-tool.cmd"
    tool.write_text(f'@"{sys.executable}" "{capture}" %*\n', encoding="utf-8")
    args = [
        "a b", "x&echo>pwned", "%PATH%", "bang!name",
        'x"&echo hacked>pwned&"', 'a\\"b', "C:\\trailing\\",
    ]
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    assert run_shell(["coverage-tool", *args], tmp_path) == 0
    assert json.loads((tmp_path / "arguments.json").read_text(encoding="utf-8")) == args
    assert not (tmp_path / "pwned").exists()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 launcher")
def test_powershell_launcher_runs_from_the_project_directory(tmp_path):
    project = tmp_path / "中文 空格 🧪 & %PATH% !"
    project.mkdir()
    (project / "sample.clj").write_text("(ns demo)\n(defn pick [] 1)\n", encoding="utf-8")
    launcher = Path(__file__).resolve().parents[1] / "crapper.ps1"
    result = subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-File", str(launcher), "--no-coverage"],
        cwd=project, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (project / ".metrics" / "crap.edn").is_file()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 launcher")
def test_powershell_launcher_preserves_root_arguments_and_threshold_status(tmp_path):
    project = tmp_path / "中文 空格 🧪 & %PATH% !"
    project.mkdir()
    (project / "sample.clj").write_text("(ns demo)\n(defn pick [] 1)\n", encoding="utf-8")
    coverage = project / "target" / "coverage"
    coverage.mkdir(parents=True)
    (coverage / "lcov.info").write_text("SF:sample.clj\nDA:2,1\nend_of_record\n", encoding="utf-8")
    launcher = Path(__file__).resolve().parents[1] / "crapper.ps1"
    result = subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-File", str(launcher),
         "--root", str(project), "--use-existing-coverage", "--threshold", "0"],
        cwd=tmp_path, capture_output=True,
    )
    assert result.returncode == 2, result.stderr
    assert "CRAP threshold exceeded" in result.stderr.decode("utf-8")
    assert (project / ".metrics" / "crap.edn").is_file()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 launcher")
def test_powershell_launcher_preserves_literal_arguments_and_native_exit_status(tmp_path):
    (tmp_path / "crapper.py").write_text(
        "import json, os, sys\n"
        "print(json.dumps({'args': sys.argv[1:], 'cwd': os.getcwd()}))\n"
        "raise SystemExit(37)\n", encoding="utf-8",
    )
    arguments = ["", 'quoted"value', "a&b", "%PATH%", "$HOME", "`tick", "bang!name", "中文 🧪", "C:\\trailing\\"]
    launcher = Path(__file__).resolve().parents[1] / "crapper.ps1"
    result = subprocess.run(
        ["pwsh", "-NoLogo", "-NoProfile", "-File", str(launcher), *arguments],
        cwd=tmp_path, capture_output=True,
    )
    assert result.returncode == 37, result.stderr
    output = json.loads(result.stdout.decode("utf-8"))
    assert output == {"args": arguments, "cwd": str(tmp_path)}


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell coverage commands")
def test_custom_coverage_command_uses_powershell_syntax_and_quoted_paths(tmp_path):
    target = tmp_path / "中文 空格 🧪 'quoted'.txt"
    path = str(target).replace("'", "''")
    command = f"$message = 'quoted \"value\"'; Set-Content -LiteralPath '{path}' -Value $message -Encoding utf8"
    assert run_shell(command, tmp_path) == 0
    assert target.read_text(encoding="utf-8").strip() == 'quoted "value"'


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell coverage commands")
def test_custom_coverage_command_preserves_native_failure_status(tmp_path):
    interpreter = sys.executable.replace("'", "''")
    assert run_shell(f"& '{interpreter}' -c 'raise SystemExit(37)'", tmp_path) == 37


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell coverage commands")
def test_custom_coverage_command_reports_powershell_errors(tmp_path):
    assert run_shell("Write-Error 'intentional failure'", tmp_path) == 1
