<#
.SYNOPSIS
Starts the local W03 review workbench.
.PARAMETER Port
Loopback port on which to serve the workbench.
.EXAMPLE
.\start-workbench.ps1 -Port 8765
#>
[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port=8765)
$ErrorActionPreference='Stop'
# config selects the existing WSL runtime; entry locates its environment launcher.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve the workbench launcher path.'}
# arguments preserves token boundaries through PowerShell and WSL.
$arguments=@('--workbench','--port',"$Port")
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) @arguments
exit $LASTEXITCODE
