[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
$scriptPath = Join-Path $PSScriptRoot 'tools/check_w01.py'
$linuxPath = & wsl.exe -d $config.distribution --exec wslpath -u $scriptPath
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the project path inside WSL.' }
& wsl.exe -d $config.distribution --exec python3 ($linuxPath.Trim())
exit $LASTEXITCODE
