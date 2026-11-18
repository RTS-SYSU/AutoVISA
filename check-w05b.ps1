<#
.SYNOPSIS
Runs real-checker acceptance for mathematical decisions and linked proposal executions.
.EXAMPLE
.\check-w05b.ps1
#>
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# @var config Existing checked WSL runtime; no installation or model API call is performed.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
# @var entry Linux launcher path passed as a separate argument.
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve continuation acceptance launcher.'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) --continuation-check
exit $LASTEXITCODE
