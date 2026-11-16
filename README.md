# crapper

CRAP scores for Clojure, Java, Go, TypeScript, Rust, Python, and C#. One run detects the language of each source file, applies that language's complexity and coverage rules, and writes the snapshot [uml-viewer](https://github.com/unclebob/uml-viewer) already reads.

The formula is the one from [crap4clj](https://github.com/unclebob/crap4clj), [crap4java](https://github.com/unclebob/crap4java), and [crap4go](https://github.com/unclebob/crap4go):

```text
CRAP = CC² × (1 − coverage)³ + CC
```

`CC` is cyclomatic complexity. `coverage` is the fraction of the function exercised by tests. A score of 1–5 is low risk, 5–30 is worth a look, and 30+ is complex and under-tested.

## Run

Requires Python 3.11 or newer. On Windows, use PowerShell 7.3 or newer (`pwsh`):

```powershell
.\crapper.ps1 --help
.\crapper.ps1 --no-coverage
# Analyze another project from the tool checkout:
.\crapper.ps1 --root ..\my-project --no-coverage
```

On Linux and macOS:

```bash
./crapper
```

The launchers create a local `.venv` and install the tool on first use. Windows uses `py -3`, falling back to `python`; Linux and macOS use `python3`. An interrupted installation is retried on the next launch. The PowerShell launcher preserves argument boundaries and does not change execution policy. Run from the project you want to analyze, or pass `--root`. The tool walks the tree, skips `test`, `spec`, `vendor`, `node_modules`, and `target`, and writes two results:

- a table on stdout, worst score first
- `.metrics/crap.edn`, replaced on every successful analysis

CLI stdout, stderr, and metric files use UTF-8, including redirected output; no `PYTHONUTF8` setting is needed. Installing the package with `python -m pip install -e /path/to/crapper` also provides the `crapper` command, and `python -m crapper` works on all three operating systems.

```bash
./crapper --no-coverage                  # complexity only; coverage is N/A
./crapper --use-existing-coverage        # read reports already on disk
./crapper src/demo/core.clj src/ui       # these files and trees
./crapper --changed                      # git additions and edits
./crapper combat                         # path fragment, same idea as crap4clj
./crapper --threshold 30                 # exit 2 when the worst score is higher
```

## Snapshot

`.metrics/crap.edn` has the same shape crap4clj writes:

```clojure
{:entries [{:name "place"
            :namespace "demo.Board"
            :complexity 3
            :coverage 75.0
            :crap 3.1}]}
```

uml-viewer groups entries by `:namespace` and joins each operation on `:name`. `nil` coverage is what `--no-coverage` writes: complexity only, and CRAP is `nil` too. A function the coverage report does not mention scores 0%.

| Language | `:namespace` | `:name` |
| --- | --- | --- |
| Clojure | the `ns` | the `defn` / `defn-` name |
| Java | `package.Class`, or `package.Outer.Inner` | the method name |
| Go | the package import path, or `import/path.Receiver` | the function or method name |
| TypeScript | the dotted module path, or `module.Class` | the function or method name |
| Rust | `crate::module`, or `crate::module::Type` | the function or method name |
| Python | the dotted module path, or `module.Class` | the function or method name |
| C# | `Namespace.Type`, including nested types | method, constructor or operator; `Property.get` / `.set` / `.init` for accessors |

Rename or move is a new entry. There is no identity matching across runs.

## What each language counts

Clojure follows crap4clj: `if` / `when` and their variants, `and`, `or`, `loop`, `catch`, and each clause of `cond`, `condp`, `case`, `cond->`, `cond->>`, `some->`, and `some->>`. Coverage prefers Cloverage's per-line form counts and falls back to LCOV.

Java follows crap4java: `if`, loops, `catch`, `?:`, each `switch` label, and `&&` / `||`. Constructors and methods inside anonymous classes are omitted. Coverage is JaCoCo's `INSTRUCTION` counter.

Go follows crap4go: `if`, `for`, `range`, each `switch` and `select` clause, and `&&` / `||`. Coverage is `go test -coverprofile`, which names each file by its module import path (the `module` line of the nearest `go.mod` plus the path inside that module). crapper and mutator look a file up by that name first, then by the longest matching path suffix.

TypeScript, TSX, and JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) use the same structural decisions as Java, including `&&` inside JSX, plus `??` and `?.`. Top-level functions, class methods, and top-level arrow functions are entries. An inline Express callback — `.get`, `.post`, `.put`, `.patch`, `.delete`, `.head`, `.options`, `.all`, `.use`, and `.route(path).get(...)` — is its own entry, named `GET /users`. A second callback on that same route is `GET /users#2`. Its decisions are not also charged to the enclosing function. Other nested callbacks stay inside the enclosing function. Coverage is LCOV. When the report has branch records (`BRDA`) inside a function, the score uses those branches; a function with no branches uses line hits. A `coverage` script is used as-is. A Vitest project runs `vitest --coverage` (installing `@vitest/coverage-v8` into `node_modules` when it is missing, without editing `package.json`). Other test scripts are wrapped in `c8`.

Rust counts `if`, loops, each `match` arm, `?`, and `&&` / `||`. `mod tests` is skipped. Coverage is LCOV from `cargo llvm-cov` or `cargo tarpaulin`, run in the nearest directory that contains `Cargo.toml`. When neither tool is installed, the run installs `cargo-llvm-cov`.

Python counts `if`, `elif`, `for`, `while`, `except`, each `match` case, a comprehension filter, a conditional expression, and each `and` / `or`. Nested functions stay inside the enclosing function. Coverage is LCOV from `coverage.py`, running pytest when the project uses it and `unittest` otherwise. `coverage` and `pytest` are installed into the project's interpreter when they are missing.

C# (`.cs`, reported as `csharp`) counts methods, constructors, destructors,
operators, conversions, executable property/indexer/event accessors, and
expression-bodied properties and indexers. Nested types retain their namespace;
explicit interface names remain on members. Automatic accessors and abstract
signatures have no body and are omitted. Local functions and lambdas stay inside
their enclosing member. Top-level statements form `Program` / `<top-level>`.
Decisions include `if`, loops, `catch`, `?:`, `&&`, `||`, `??`, `??=`, pattern
`and` / `or`, non-default switch cases and expression arms, and `when` guards.
Coverage uses Cobertura branch counts when present, otherwise executable line
hits, and also accepts LCOV.

C# uses the selected .NET SDK's Roslyn parser through the shared
`crapper.frontend.parse_document` API, also consumed by Dryer and Mutator.
The first run builds a small host in the operating system's temporary directory;
no NuGet parser package or global tool installation is required. Other languages
retain their existing Tree-sitter parsers. Native syntax kinds and UTF-8 source
spans are preserved; common roles and executable units connect them to the
existing analysis algorithms.

For a source file beneath one `.csproj`, the frontend reads `LangVersion` and
`DefineConstants`, including SDK framework symbols, using MSBuild. CLI analysis
uses Debug and the first target framework for a multi-targeted project. The
Python API accepts explicit `configuration`, `target_framework`,
`language_version` and `symbols`. Loose source uses the selected compiler's
default language version, no extra symbols and explicit file-based program
support for `#:` directives. Syntax errors stop analysis with
a compiler diagnostic; parsing alone does not validate types, overloads or the
availability of every feature in an older language version.

Default discovery skips .NET `bin`, `obj`, `TestResults`, `.artifacts`, `.vs`,
and `BenchmarkDotNet.Artifacts` output directories. Generated `.g.cs`, `.g.i.cs`
and `.Designer.cs` filenames are omitted regardless of case. C# files in
`*.Test` / `*.Tests` directories (case insensitive), PascalCase `*Test.cs` /
`*Tests.cs`, and `_test.cs` / `_tests.cs` names follow the normal test exclusion;
explicit file arguments include tests. Names such as `Contest.cs` and
`Latest.TestsData` remain production source.

## Coverage commands

By default a run deletes the previous report for each language it is about to measure and regenerates it:

| Language | Command | Report |
| --- | --- | --- |
| Clojure | `clj -M:cov --lcov` (needs `deps.edn` or `bb.edn`) | `target/coverage/` |
| Java | JaCoCo Maven plugin `0.8.12` in each module with `pom.xml` | `target/site/jacoco/jacoco.xml` |
| Go | `go test ./... -coverprofile=...` | `target/coverage/go/coverage.out` |
| TypeScript | `npm run coverage`, or Vitest `--coverage`, or `npx c8 ... npm test` | `coverage/lcov.info` or `target/coverage/typescript/lcov.info` |
| Rust | `cargo llvm-cov` or `cargo tarpaulin`, per Cargo package | `target/coverage/rust/lcov.info` |
| Python | `coverage run` with pytest or unittest, then `coverage lcov` | `target/coverage/python/lcov.info` |
| C# | `dotnet test --collect "XPlat Code Coverage"`, or native MTP `--coverage --coverage-output-format cobertura` | `target/coverage/csharp/**/*.cobertura.xml` |

The C# default detects `global.json`'s `test.runner`. VSTest requires the
project's `coverlet.collector` package; Microsoft.Testing.Platform requires
`Microsoft.Testing.Extensions.CodeCoverage`. MTP results use a separate module
directory so concurrently tested projects do not overwrite each other's report.
The tool does not edit project files or install a collector. A missing collector
or absent report produces a diagnostic. See the official
[MTP coverage documentation](https://learn.microsoft.com/en-us/dotnet/core/testing/microsoft-testing-platform-code-coverage).

An existing [dotnet-coverage](https://learn.microsoft.com/en-us/dotnet/core/additional-tools/dotnet-coverage)
installation can collect coverage without adding a package to each test project:

```powershell
.\crapper.ps1 --root ..\my-project --coverage-command 'dotnet-coverage collect -f cobertura -o target/coverage/csharp/coverage.cobertura.xml dotnet test'
```

`--use-existing-coverage` also finds `*.cobertura.xml` under `coverage` and
project `TestResults` directories. Reports retain source path ownership when
several files have the same basename. Multiple classes in one source file and
multiple reports merge line hits without replacing covered lines with misses;
branch counts retain the best reported coverage at each line. Invalid XML and
invalid line records are ignored so other reports remain usable.

A missing tool or a failed test run scores that language at 0% and still writes the snapshot. Pass `--coverage-command` to replace those defaults with one command of your own. `--no-coverage` is the run that leaves coverage and CRAP as N/A.

Coverage requires the project's language toolchain on `PATH`. Windows command shims such as `npm.cmd` and `mvn.cmd` are resolved automatically. Python coverage prefers the project's `.venv` or `venv` interpreter (`Scripts/python.exe` on Windows, `bin/python` on Linux/macOS), falling back to the interpreter running crapper. On Windows, `--coverage-command` uses PowerShell 7.3+ syntax; Linux/macOS use the platform's shell. For a quoted executable path in PowerShell, use the call operator: `--coverage-command "& '.\my tools\runner.exe' --coverage"`. Native failure exit codes are preserved, and PowerShell errors fail the coverage command.

Tree-sitter language packs that download parsers fetch each required grammar on first use and then cache it. Bundled language-pack releases are also supported.

## Development

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

Linux and macOS:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

The GitHub Actions test matrix covers Windows, Linux, and macOS on Python 3.11 and 3.13. The optional EDN reader integration check requires `bb` (Babashka); the legacy `uml` viewer launcher check requires zsh. The viewer launcher itself still targets zsh.
