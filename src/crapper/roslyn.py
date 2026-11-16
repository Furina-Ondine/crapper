"""Run the SDK's C# parser in one persistent, isolated compiler process.

The small host is compiled without NuGet packages into a content-addressed
temporary cache. The target project and global installations are not changed.
"""

import atexit
import errno
import hashlib
import json
import re
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path


_HOST = Path(__file__).with_name("roslyn_host")
_LOCK = threading.RLock()


def _run(arguments, cwd):
    try:
        result = subprocess.run(arguments, cwd=cwd, capture_output=True, encoding="utf-8")
    except FileNotFoundError as error:
        raise RuntimeError("C# analysis requires an installed .NET SDK (dotnet).") from error
    if result.returncode:
        raise RuntimeError(f"C# frontend command failed: {' '.join(map(str, arguments))}\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


@lru_cache(maxsize=32)
def _sdk(cwd):
    version = _run(["dotnet", "--version"], cwd)
    installed = _run(["dotnet", "--list-sdks"], cwd)
    for line in installed.splitlines():
        match = re.fullmatch(r"(\S+) \[(.+)\]", line.strip())
        if match and match[1] == version:
            return Path(match[2]) / version
    raise RuntimeError(f"Selected .NET SDK {version} was not found in dotnet --list-sdks.")


def _fingerprint(sdk):
    digest = hashlib.sha256(str(sdk).encode())
    for path in sorted(_HOST.glob("*")):
        if path.suffix in {".cs", ".csproj"}:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:24]


@lru_cache(maxsize=8)
def _build(sdk, fingerprint):
    cache = Path(tempfile.gettempdir()) / "ub-mode" / "roslyn"
    destination = cache / fingerprint
    binary = destination / "RoslynHost.dll"
    if binary.exists():
        return binary
    cache.mkdir(parents=True, exist_ok=True)
    # Each concurrent caller builds in its own directory; publish only a complete host.
    with tempfile.TemporaryDirectory(prefix="build-", dir=cache) as directory:
        scratch = Path(directory)
        output = scratch / "out"
        framework = f"net{sdk.name.split('.')[0]}.0"
        _run(["dotnet", str(sdk / "MSBuild.dll"), str(_HOST / "RoslynHost.csproj"),
              "-restore", "-nologo", "-verbosity:quiet", "-nodeReuse:false", f"-p:TargetFramework={framework}",
              f"-p:RoslynDir={sdk / 'Roslyn' / 'bincore'}", f"-p:OutputPath={output}/",
              f"-p:BaseIntermediateOutputPath={scratch / 'obj'}/", "-p:UseSharedCompilation=false",
              "-p:RestoreIgnoreFailedSources=true"], _HOST)
        try:
            output.rename(destination)
        except OSError as error:
            if error.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not binary.exists():
                raise
    return binary


def _project_for(path, project_root):
    source = Path(project_root or Path.cwd()) / path
    boundary = Path(project_root).resolve() if project_root else None
    for directory in source.resolve().parents:
        projects = sorted(directory.glob("*.csproj"))
        if projects:
            if len(projects) == 1:
                return projects[0]
            raise RuntimeError(f"Multiple C# projects beside {source}; specify an unambiguous project layout.")
        if directory == boundary:
            break
    return None


def _properties(project, configuration, target_framework, implicit):
    args = ["dotnet", "msbuild", str(project), "-nologo",
            "-getProperty:LangVersion,DefineConstants,TargetFramework,TargetFrameworks",
            f"-p:Configuration={configuration}"]
    if target_framework:
        args.append(f"-p:TargetFramework={target_framework}")
    if implicit:
        args.append("-target:AddImplicitDefineConstants")
    return json.loads(_run(args, project.parent))["Properties"]


@lru_cache(maxsize=64)
def _project_options(project, configuration, target_framework):
    initial = _properties(project, configuration, target_framework, False)
    framework = initial["TargetFramework"] or initial["TargetFrameworks"].split(";")[0]
    properties = _properties(project, configuration, framework, True)
    return properties["LangVersion"] or None, tuple(filter(None, properties["DefineConstants"].split(";")))


class _Host:
    def __init__(self, binary):
        self.process = subprocess.Popen(
            ["dotnet", str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, encoding="utf-8",
        )

    def parse(self, request):
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            self.process.wait()
            raise RuntimeError(f"C# compiler frontend stopped: {self.process.stderr.read()}")
        return json.loads(line)

    def close(self):
        self.process.stdin.close()
        if self.process.poll() is None:
            self.process.wait(timeout=10)
        self.process.stdout.close()
        self.process.stderr.close()


_HOSTS = {}


@atexit.register
def _close_hosts():
    for host in _HOSTS.values():
        host.close()


def _context_directory(project, project_root):
    context = project.parent if project else Path(project_root or Path.cwd())
    return context if context.is_dir() else Path.cwd()


def _effective_options(project, configuration, target_framework, language_version, symbols):
    if project is None or language_version is not None and symbols is not None:
        return language_version, symbols
    version, constants = _project_options(project, configuration, target_framework)
    return (version if language_version is None else language_version,
            constants if symbols is None else symbols)


def _host_for(sdk):
    binary = _build(sdk, _fingerprint(sdk))
    if binary in _HOSTS and _HOSTS[binary].process.poll() is not None:
        _HOSTS.pop(binary).close()
    if binary not in _HOSTS:
        _HOSTS[binary] = _Host(binary)
    return _HOSTS[binary]


def parse_source(source, path, project_root=None, *, language_version=None,
                 symbols=None, configuration="Debug", target_framework=None):
    project = _project_for(path, project_root)
    language_version, symbols = _effective_options(
        project, configuration, target_framework, language_version, symbols)
    with _LOCK:
        host = _host_for(_sdk(str(_context_directory(project, project_root))))
        return host.parse({"path": path, "source": source,
                           "languageVersion": language_version, "symbols": symbols or (),
                           "fileBasedProgram": project is None})
