"""Run the selected .NET SDK's C# parser in a small persistent process."""

import atexit
import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import Lock


class CSharpHostError(RuntimeError):
    """The SDK or parsing process could not provide a C# syntax tree."""


_HOST = Path(__file__).with_name("roslyn_host")
_LOCK = Lock()
_CLIENTS = {}


def _run(args, cwd):
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace",
            env={**os.environ, "DOTNET_ADD_GLOBAL_TOOLS_TO_PATH": "false", "DOTNET_NOLOGO": "1"},
        )
    except FileNotFoundError as error:
        raise CSharpHostError("C# analysis requires an installed .NET SDK (dotnet).") from error
    except OSError as error:
        raise CSharpHostError(f"Cannot run the .NET SDK in {cwd}: {error}") from error
    if result.returncode:
        raise CSharpHostError(f"C# SDK command failed in {cwd}: {result.stdout}{result.stderr}".strip())
    return result.stdout.strip()


@lru_cache(maxsize=32)
def _sdk(cwd):
    version = _run(["dotnet", "--version"], cwd)
    for line in _run(["dotnet", "--list-sdks"], cwd).splitlines():
        match = re.fullmatch(r"(\S+) \[(.+)\]", line.strip())
        if match and match[1] == version:
            return Path(match[2]) / version
    raise CSharpHostError(f"Selected .NET SDK {version} was not found in dotnet --list-sdks.")


def _host_binary(sdk):
    sources = sorted(path for path in _HOST.iterdir() if path.suffix in {".cs", ".csproj"})
    digest = hashlib.sha256(str(sdk).encode("utf-8"))
    for source in sources:
        digest.update(source.name.encode("utf-8"))
        digest.update(source.read_bytes())
    cache = Path(tempfile.gettempdir()) / "ub-mode" / "roslyn"
    destination = cache / digest.hexdigest()[:24]
    binary = destination / "RoslynHost.dll"
    if binary.is_file():
        return binary
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="build-", dir=cache) as directory:
        scratch = Path(directory)
        output = scratch / "out"
        for source in sources:
            shutil.copy2(source, scratch / source.name)
        framework = f"net{sdk.name.split('.')[0]}.0"
        _run([
            "dotnet", str(sdk / "MSBuild.dll"), str(scratch / "RoslynHost.csproj"),
            "-restore", "-nologo", "-verbosity:quiet", "-nodeReuse:false",
            f"-p:TargetFramework={framework}", f"-p:RoslynDir={sdk / 'Roslyn' / 'bincore'}",
            f"-p:OutputPath={output}/", "-p:UseSharedCompilation=false",
            "-p:RestoreIgnoreFailedSources=true",
        ], scratch)
        try:
            output.rename(destination)
        except OSError as error:
            if error.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not binary.is_file():
                raise
    return binary


def _project_for(source, boundary):
    for directory in source.parents:
        projects = sorted(directory.glob("*.csproj"))
        if len(projects) > 1:
            raise CSharpHostError(f"Multiple C# projects beside {source}; project context is ambiguous.")
        if projects:
            return projects[0]
        if directory == boundary:
            break
    return None


def _properties(project, *options):
    output = _run([
        "dotnet", "msbuild", str(project), "-nologo", "-p:Configuration=Debug",
        "-getProperty:LangVersion,DefineConstants,TargetFramework,TargetFrameworks", *options,
    ], project.parent)
    try:
        return json.loads(output)["Properties"]
    except (KeyError, json.JSONDecodeError) as error:
        raise CSharpHostError(f"MSBuild returned unexpected C# project properties for {project}: {output}") from error


@lru_cache(maxsize=64)
def _project_options(project):
    initial = _properties(project)
    framework = initial["TargetFramework"] or initial["TargetFrameworks"].split(";")[0]
    properties = _properties(project, f"-p:TargetFramework={framework}", "-target:AddImplicitDefineConstants")
    symbols = tuple(symbol.strip() for symbol in re.split(r"[;,]", properties["DefineConstants"]) if symbol.strip())
    return properties["LangVersion"] or None, symbols


class _Client:
    def __init__(self, binary):
        self.process = subprocess.Popen(
            ["dotnet", str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, encoding="utf-8",
        )

    def parse(self, request):
        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()
        except BrokenPipeError:
            pass
        line = self.process.stdout.readline()
        if not line:
            self.process.wait()
            raise CSharpHostError(f"C# parser stopped: {self.process.stderr.read()}".strip())
        return json.loads(line)

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()
        self.process.stderr.close()


@atexit.register
def _close_clients():
    for client in _CLIENTS.values():
        client.close()


def _client(sdk):
    existing = _CLIENTS.get(sdk)
    if existing is not None and existing.process.poll() is not None:
        _CLIENTS.pop(sdk).close()
    if sdk not in _CLIENTS:
        _CLIENTS[sdk] = _Client(_host_binary(sdk))
    return _CLIENTS[sdk]


def parse_source(source, path, project_root):
    boundary = Path(project_root).resolve() if project_root is not None else None
    location = ((boundary or Path.cwd()) / path).resolve()
    project = _project_for(location, boundary)
    if project is None:
        context = next(parent for parent in location.parents if parent.is_dir())
        version, symbols = None, ()
    else:
        context = project.parent
        version, symbols = _project_options(project)
    try:
        with _LOCK:
            return _client(_sdk(context)).parse({
                "path": str(path), "source": source, "languageVersion": version,
                "symbols": symbols, "fileBasedProgram": project is None,
            })
    except (OSError, json.JSONDecodeError) as error:
        raise CSharpHostError(f"C# parser could not read {path}: {error}") from error
