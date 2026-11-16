#requires -Version 7.3
param(
    [Parameter(Mandatory)][string]$SdkDirectory,
    [Parameter(Mandatory)][string]$TargetFramework,
    [Parameter(Mandatory)][string]$Python
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot
$taskProject = Join-Path $taskRoot 'RoslynHost.csproj'
$taskCompiler = Join-Path $SdkDirectory 'Roslyn/bincore'
$taskOutput = Join-Path $taskRoot 'target/bin/'
$taskIntermediate = Join-Path $taskRoot 'target/obj/'
& dotnet (Join-Path $SdkDirectory 'MSBuild.dll') $taskProject -restore -nologo -verbosity:quiet -nodeReuse:false `
    "-p:TargetFramework=$TargetFramework" "-p:RoslynDir=$taskCompiler" `
    "-p:BaseIntermediateOutputPath=$taskIntermediate" "-p:OutputPath=$taskOutput" `
    -p:Configuration=Release -p:UseSharedCompilation=false -p:NuGetAudit=false -p:RestoreIgnoreFailedSources=true
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python (Join-Path $PSScriptRoot 'protocol_test.py') (Join-Path $taskOutput 'RoslynHost.dll')
exit $LASTEXITCODE
