<#
.SYNOPSIS
Checks independent MSA input, immutable review and supported formal mappings.
#>
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
# @var config Existing WSL toolchain selection.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw|ConvertFrom-Json
# @var entry Linux launcher path, passed without concatenating shell source.
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Cannot resolve MSA launcher.'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) --msa-check
exit $LASTEXITCODE
