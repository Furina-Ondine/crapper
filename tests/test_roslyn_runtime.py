"""User-visible failures from the compiler integration."""

import errno

import pytest

from crapper.frontend import parse_document
from crapper import roslyn


def test_missing_dotnet_reports_sdk_requirement(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError('dotnet')

    monkeypatch.setattr(roslyn.subprocess, 'run', missing)
    roslyn._sdk.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=r'C# analysis requires an installed .NET SDK'):
            parse_document('class MissingSdk {}', 'csharp', str(tmp_path / 'Missing.cs'), project_root=str(tmp_path))
    finally:
        roslyn._sdk.cache_clear()


def test_sdk_inventory_uses_the_version_selected_by_dotnet(tmp_path, monkeypatch):
    def inventory(arguments, cwd):
        if arguments[-1] == "--version":
            return "10.0.400"
        return "10.0.303 [C:/dotnet/sdk]\n10.0.400 [C:/dotnet/sdk]"

    monkeypatch.setattr(roslyn, "_run", inventory)
    assert roslyn._sdk(str(tmp_path)).as_posix() == "C:/dotnet/sdk/10.0.400"


def test_sdk_inventory_rejects_an_absent_selected_version(tmp_path, monkeypatch):
    monkeypatch.setattr(roslyn, "_run", lambda arguments, cwd: "10.0.400" if arguments[-1] == "--version" else "10.0.303 [C:/dotnet/sdk]")
    with pytest.raises(RuntimeError, match="10.0.400 was not found"):
        roslyn._sdk(str(tmp_path))


def test_concurrent_first_use_shares_compiler_cache(tmp_path):
    import os
    import subprocess
    import sys
    import time

    cache = tmp_path / 'shared-temp'
    cache.mkdir()
    gate = tmp_path / 'start'
    script = '''
import pathlib, sys, time
from crapper.frontend import parse_document
ready, gate = map(pathlib.Path, sys.argv[1:])
ready.touch()
deadline = time.monotonic() + 30
while not gate.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("start gate timed out")
    time.sleep(0.02)
document = parse_document("class Concurrent { int F() => 1; }", "csharp", "Concurrent.cs")
assert [(unit.namespace, unit.name) for unit in document.units] == [("Concurrent", "F")]
print("ok")
'''
    environment = os.environ.copy()
    environment.update(TEMP=str(cache), TMP=str(cache), PYTHONUTF8='1')
    processes = []
    try:
        for index in range(4):
            ready = tmp_path / f'ready-{index}'
            processes.append(subprocess.Popen(
                [sys.executable, '-c', script, str(ready), str(gate)],
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8',
            ))
        deadline = time.monotonic() + 30
        while not all((tmp_path / f'ready-{index}').exists() for index in range(4)):
            if any(process.poll() is not None for process in processes):
                pytest.fail('a compiler client exited before the start gate')
            if time.monotonic() >= deadline:
                pytest.fail('compiler clients did not reach the start gate')
            time.sleep(0.02)
        gate.touch()
        deadline = time.monotonic() + 120
        for process in processes:
            stdout, stderr = process.communicate(timeout=max(0.1, deadline - time.monotonic()))
            assert process.returncode == 0, stderr
            assert stdout.strip() == 'ok'
    finally:
        for process in processes:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   capture_output=True, timeout=10, check=False)
                if process.poll() is None:
                    process.kill()
            process.communicate(timeout=10)


def test_host_build_ignores_unrelated_assemblies_in_source_tree(tmp_path, monkeypatch):
    import hashlib
    import shutil
    import subprocess
    import tempfile

    sdk = roslyn._sdk(str(tmp_path))
    host = tmp_path / 'host'
    host.mkdir()
    for source in roslyn._HOST.iterdir():
        if source.suffix in {'.cs', '.csproj'}:
            shutil.copy2(source, host / source.name)
    fake = tmp_path / 'fake'
    fake.mkdir()
    framework = f"net{sdk.name.split('.')[0]}.0"
    (fake / 'Fake.csproj').write_text(
        f'<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>{framework}</TargetFramework>'
        '<AssemblyName>Microsoft.CodeAnalysis.CSharp</AssemblyName><AssemblyVersion>99.0.0.0</AssemblyVersion>'
        '</PropertyGroup></Project>', encoding='utf-8')
    (fake / 'Fake.cs').write_text('public class Fake {}', encoding='utf-8')
    subprocess.run(['dotnet', 'build', str(fake / 'Fake.csproj'), '-o', str(host / 'target' / 'bin'),
                    '-nologo', '-verbosity:quiet'], cwd=tmp_path, check=True, capture_output=True, timeout=120)
    cache = tmp_path / 'cache'
    cache.mkdir()
    monkeypatch.setattr(roslyn, '_HOST', host)
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(cache))
    roslyn._build.cache_clear()
    try:
        binary = roslyn._build(sdk, roslyn._fingerprint(sdk))
        actual = (binary.parent / 'Microsoft.CodeAnalysis.CSharp.dll').read_bytes()
        expected = (sdk / 'Roslyn' / 'bincore' / 'Microsoft.CodeAnalysis.CSharp.dll').read_bytes()
        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()
        client = roslyn._Host(binary)
        try:
            result = client.parse({'path': 'Sample.cs', 'source': 'class C { int F() => 1; }',
                                   'languageVersion': None, 'symbols': []})
            assert [unit['name'] for unit in result['units']] == ['F']
        finally:
            client.close()
    finally:
        roslyn._build.cache_clear()


@pytest.mark.parametrize('error_code,publish,accepted', [(errno.ENOTEMPTY, True, True), (errno.EEXIST, True, True), (errno.EACCES, True, False), (errno.ENOTEMPTY, False, False)])
def test_cache_publication_only_accepts_a_complete_concurrent_winner(tmp_path, monkeypatch, error_code, publish, accepted):
    import tempfile
    from pathlib import Path
    from crapper.frontend import parse_document

    # ENOTEMPTY is used by POSIX rename when another directory has already won.
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))
    rename = Path.rename
    def competing_publication(source, destination):
        if publish:
            rename(source, destination)
        raise OSError(error_code, 'simulated publication boundary')
    monkeypatch.setattr(Path, 'rename', competing_publication)
    roslyn._build.cache_clear()
    try:
        if accepted:
            document = parse_document('class Published { int Run() => 1; }', 'csharp', str(tmp_path / 'Published.cs'))
            assert [unit.name for unit in document.units] == ['Run']
        else:
            with pytest.raises(OSError) as failure:
                parse_document('class Rejected { int Run() => 1; }', 'csharp', str(tmp_path / 'Rejected.cs'))
            assert failure.value.errno == error_code
    finally:
        roslyn._build.cache_clear()
