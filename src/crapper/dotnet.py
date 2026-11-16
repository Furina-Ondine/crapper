"""Choose the .NET test host's coverage arguments without editing projects."""

import json
from pathlib import Path

from crapper.discover import SKIP_DIRS


def uses_mtp(root: Path) -> bool:
    for directory in [root, *root.parents]:
        file = directory / "global.json"
        if file.is_file():
            data = json.loads(file.read_text(encoding="utf-8-sig"))
            return data.get("test", {}).get("runner") == "Microsoft.Testing.Platform"
    return False


def test_directories(root: Path) -> list[Path]:
    if any(root.glob("*.sln")) or any(root.glob("*.slnx")) or any(root.glob("*.csproj")):
        return [root]
    projects = root.rglob("*.csproj")
    return sorted({project.parent for project in projects if not SKIP_DIRS.intersection(project.relative_to(root).parts)})


def coverage_command(directory: Path, report: Path) -> list[str]:
    command = ["dotnet", "test", "--results-directory", str(report)]
    if uses_mtp(directory):
        return command + ["--results-directory-layout", "per-module", "--coverage",
                          "--coverage-output-format", "cobertura", "--coverage-output", "coverage.cobertura.xml"]
    return ["dotnet", "test", "--collect", "XPlat Code Coverage", "--results-directory", str(report)]
