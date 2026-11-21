"""Find source files and decide which language each one is written in."""

import os
from pathlib import Path

EXTENSIONS = {
    ".clj": "clojure",
    ".cljc": "clojure",
    ".cljs": "clojure",
    ".bb": "clojure",
    ".java": "java",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".mjs": "typescript",
    ".cjs": "typescript",
    ".rs": "rust",
    ".py": "python",
    ".cs": "csharp",
}

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "out",
    "coverage",
    ".metrics",
    "testdata",
    "__pycache__",
    ".clj-kondo",
}

TEST_DIRS = {"test", "tests", "spec", "specs", "__tests__"}
C_SHARP_OUTPUT_DIRS = {"bin", "obj", "testresults", ".artifacts", ".vs", "benchmarkdotnet.artifacts"}

GO_TEST_SUFFIX = "_test.go"
CLOJURE_TEST_SUFFIXES = ("_test.clj", "_test.cljc", "_test.cljs", "_test.bb")
JS_TEST_SUFFIXES = (
    ".test.ts",
    ".spec.ts",
    ".test.tsx",
    ".spec.tsx",
    ".test.mts",
    ".spec.mts",
    ".test.cts",
    ".spec.cts",
    ".test.js",
    ".spec.js",
    ".test.jsx",
    ".spec.jsx",
    ".test.mjs",
    ".spec.mjs",
    ".test.cjs",
    ".spec.cjs",
)


def language_of(path: str | Path) -> str | None:
    file_path = Path(path)
    name = file_path.name
    if name.endswith(".d.ts"):
        return None
    if name.lower().endswith((".g.cs", ".g.i.cs", ".designer.cs")):
        return None
    return EXTENSIONS.get(file_path.suffix)


def _is_csharp_test(path: Path) -> bool:
    return (
        path.stem.endswith(("Test", "Tests"))
        or path.stem.lower().endswith(("_test", "_tests"))
        or any(part.lower().endswith((".test", ".tests")) for part in path.parts[:-1])
    )


def is_test_file(path: str | Path) -> bool:
    file_path = Path(path)
    name = file_path.name
    if file_path.suffix == ".cs" and _is_csharp_test(file_path):
        return True
    if name.endswith(GO_TEST_SUFFIX):
        return True
    if name.endswith(CLOJURE_TEST_SUFFIXES):
        return True
    if name.endswith(JS_TEST_SUFFIXES):
        return True
    if name == "conftest.py":
        return True
    if name.endswith("_test.py") or (name.startswith("test_") and name.endswith(".py")):
        return True
    return any(part in TEST_DIRS for part in file_path.parts)


def is_production_source(path: str | Path) -> bool:
    """Check source conventions for directory walks and changed-file selection."""
    language = language_of(path)
    if language is None or is_test_file(path):
        return False
    return language != "csharp" or not any(
        part.lower() in C_SHARP_OUTPUT_DIRS for part in Path(path).parts[:-1]
    )


def _walk(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames if name not in SKIP_DIRS and name not in TEST_DIRS
        ]
        for name in filenames:
            path = Path(dirpath) / name
            if not is_production_source(path):
                continue
            found.append(path)
    return found


def iter_source_files(roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in roots:
        for path in _walk(root):
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.as_posix())
