<#
.SYNOPSIS
Runs W02 acceptance or prints the saved history of one goal.
.PARAMETER Goal
Logical goal name, such as joint-demo. Omit to run acceptance and publish a new report.
.OUTPUTS
Acceptance progress and result text, or a JSON history when Goal is supplied.
.EXAMPLE
.\check-w02.ps1 -Goal joint-demo
#>
[CmdletBinding()]
param([string]$Goal)
$ErrorActionPreference = 'Stop'
# config supplies the WSL distribution selected for this project.
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
# entry is the Windows script path; path is its translated Linux path in that distribution.
$entry = Join-Path $PSScriptRoot 'tools/w02_env.sh'
$path = & wsl.exe -d $config.distribution --exec wslpath -u $entry
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the W02 entry point inside WSL.' }
# A named goal opens a restored database snapshot; a plain invocation starts a fresh acceptance run.
# arguments preserves the goal name as a single command-line argument across the WSL boundary.
$arguments = @()
if ($Goal) { $arguments = @('--show', $Goal) }
& wsl.exe -d $config.distribution --exec bash ($path.Trim()) @arguments
exit $LASTEXITCODE

