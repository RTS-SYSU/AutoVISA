<#
.SYNOPSIS
Starts the local W03 review workbench or its isolated acceptance suite.
.PARAMETER Port
Loopback port on which to serve the workbench.
.PARAMETER Check
Run isolated Web and revision acceptance instead of serving.
.PARAMETER Testing
Use a separate catalog with a visible acceptance label.
.PARAMETER W04Demo
Open an isolated demo populated from the latest successful W04 acceptance.
.PARAMETER W05bDemo
Open an isolated demo populated with W05-b decisions and linked executions.
.PARAMETER W05cDemo
Open an isolated demo populated with version-bound parent/child comparisons.
.PARAMETER W06Demo
Open an isolated demo populated with checked service lemmas and open capacity obligations.
.PARAMETER MsaDemo
Open an isolated MSA demo with genuine arithmetic and Prosa proof evidence.
.EXAMPLE
.\start-workbench.ps1 -Port 8765
#>
[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port=8765,[switch]$Check,[switch]$Testing,[switch]$W04Demo,[switch]$W05bDemo,[switch]$W05cDemo,[switch]$W06Demo,[switch]$MsaDemo)
$ErrorActionPreference='Stop'
# config selects the existing WSL runtime; entry locates its environment launcher.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve the workbench launcher path.'}
# arguments preserves token boundaries through PowerShell and WSL.
$arguments=@('--workbench','--port',"$Port")
if($Check){$arguments+='--check'}
if($Testing){$arguments+='--testing'}
if($W04Demo){$arguments+='--w04-demo'}
if($W05bDemo){$arguments+='--w05b-demo'}
if($W05cDemo){$arguments+='--w05c-demo'}
if($W06Demo){$arguments+='--w06-demo'}
if($MsaDemo){$arguments+='--msa-demo'}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) @arguments
exit $LASTEXITCODE
