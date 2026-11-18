<#
.SYNOPSIS
Runs real-checker acceptance for version-bound parent/child comparisons with original evidence.
.EXAMPLE
.\check-w05c.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# @var config Existing checked WSL runtime; no installation or model API call is performed.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
# @var entry Linux launcher path passed as a separate argument.
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve comparison acceptance launcher.'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) --comparison-check
exit $LASTEXITCODE
