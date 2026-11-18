<#
.SYNOPSIS
Runs real Rocq service proofs, preserves open obligations and restores the result independently.
.EXAMPLE
.\check-w06.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# @var config Existing fixed WSL toolchain; no packages or external model calls are installed.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
# @var entry Launcher path passed as a single argument to the configured distribution.
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve W06 acceptance launcher.'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) --service-proof-check
exit $LASTEXITCODE
