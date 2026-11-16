# C# implementation log

The change adds executable C# member analysis and real .NET coverage input while
keeping the existing CRAP snapshot contract. Development follows the installed
ub-mode skill.

1. Inspected discovery, tree-sitter readers, the shared function model, coverage
   loading and coverage command selection. The working tree was clean on
   `master`; no previous portability PR was changed or pushed.
2. Added five public behavior tests for member names and spans, decisions,
   local function ownership, operators and discovery. All five first failed
   because C# was unsupported. Added the reader and `.cs` registration; corrected
   an invalid namespace fixture and observed all five pass.
3. Added Cobertura loader tests through `load_bundle`. Three tests failed before
   the implementation; all four then passed, including path ambiguity checks.
4. Added three failing default coverage runner tests, then implemented VSTest and
   native MTP collector argument selection. The 12 combined C# tests passed.
   Consulted Microsoft documentation for the different test-host arguments and
   collector package prerequisites.
5. Added failing tests for top-level statements, explicit interface properties,
   and generated filenames; implemented each behavior. A real grammar probe
   identified modern C# switch sections; a failing complexity test (2 instead of
   5) drove the correction for case labels and guards.
6. Added malformed-report cases and observed two XML parse failures; isolated
   malformed Cobertura reports so valid reports are retained.
7. Ran the complete suite and collected Python branch coverage. Self-analysis
   found `run_coverage` at CRAP 10 after adding the seventh language. Replaced its
   repeated language decisions with one dispatch table to keep it below 10.
8. Ran Dryer at threshold 0.8 on changed modules: no duplicate candidates.
9. Executed Mutator against both new Python modules. The first run exposed three
   survivors: two top-level byte-end changes and one project output-directory
   filter change. Added end-span and multiple-project discovery assertions;
   all 37 sites were then killed. The final gate reruns after subsequent edits.
10. Added .NET output-directory and C# test-name conventions, with seven observed
    behavior failures before implementing exclusions. Explicit named test files
    remain analyzable and similar production names remain included.

Final gate results and real-project validation are recorded after the remaining
integration review. Earlier scan results alone do not establish .NET coverage or
mutation execution support.

## Shared compiler frontend and final verification

The legal ref-return assignment `Unsafe.Add(...) = value` exposed a real
Tree-sitter grammar gap in Metaheuristics.NET. The implementation now uses one
SDK Roslyn host behind `parse_document`, rather than extending three private
C# walkers. Native compiler kinds, UTF-8 byte spans, diagnostics and executable
units are shared; complexity, duplicate fingerprints and mutation execution keep
their existing algorithms. Other languages retain Tree-sitter.

Tests pinned malformed input, Unicode/CRLF coordinates, modern executable
members, visibility, language versions and preprocessor symbols before the
frontend replacement. MSBuild supplies the nearest project's language version
and constants, including framework symbols. A cold-cache four-process test
checks complete, atomic cache publication. Publication accepts both EEXIST and
ENOTEMPTY from a completed concurrent winner and propagates unrelated failures.

A real four-repository audit exposed stale Roslyn DLLs in a local build folder
being selected ahead of the requested SDK reference. The host now disables
implicit file inclusion and explicitly includes only its sources and SDK
references. A regression first reproduced the problem with a real fake assembly,
then verified that the cached DLL hash matches the selected SDK. The wheel ships
host source only; isolated extraction and first compilation were also exercised.

The runtime corpus also supplied a real file-based program using `#:` directives.
Loose source now explicitly enables Roslyn's FileBasedProgram feature; sources
with a project keep the project's options. Protocol tests first pinned rejection
in project context and acceptance in file-based context. All project-less files
in the four repositories were parsed again after this correction.

Cobertura and LCOV share the existing coverage model. The public
`CoverageBundle.line_record_for` and source binding also let Mutator apply the
same ambiguous-path policy without maintaining another matcher. Default fresh
reports replace older inputs for that language; failed collection cannot reuse a
stale report or delete the project's existing TestResults.

Earlier mutation counts above predate the unchanged-worker control and are
superseded. Final Python self-mutation checks first run the identical tests in
an unchanged private worker; launcher integration is checked separately in the
complete suite. The full regression passes 232 tests with two platform skips,
including the host's 14 protocol cases. Changed Python functions have 112 killed supported sites after
removing redundant path/framework choices. The host's supported mutation pass
has 48 killed and 15 compiler-invalid sites; invalid programs are not kills.

The linked workspace validation log records the complete regression and corpus
results. Syntax success establishes compiler parsing, not type binding or every
project's configuration. Multiple adjacent project files, unavailable generated
imports and intentionally selected `#error` branches are reported as diagnostics.
