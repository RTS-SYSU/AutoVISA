<#
.SYNOPSIS
Runs isolated W05-a feedback, proposal and restoration acceptance.
.EXAMPLE
.\check-w05a.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# @var config Existing WSL distribution used by the project's checked runtime.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
# @var entry Argument-safe Linux path to the shared environment launcher.
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve feedback acceptance launcher.'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) --feedback-check
exit $LASTEXITCODE
