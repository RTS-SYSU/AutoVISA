<#
.SYNOPSIS
Maps a frozen semantic context to typed Analysis IR and a checked Rocq declaration.
.PARAMETER Freeze
Frozen review identity to map.
.PARAMETER Receipt
Existing mapping receipt to reopen and export.
.PARAMETER Check
Run isolated mapping, real Rocq and database-restoration acceptance.
#>
[CmdletBinding(DefaultParameterSetName='Freeze')]
param(
    [Parameter(Mandatory,ParameterSetName='Freeze')][string]$Freeze,
    [Parameter(Mandatory,ParameterSetName='Receipt')][string]$Receipt,
    [Parameter(Mandatory,ParameterSetName='Check')][switch]$Check
)
$ErrorActionPreference='Stop'
# config selects the existing WSL environment; entry resolves its shared runtime launcher.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw|ConvertFrom-Json
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve the mapping launcher.'}
# arguments preserves each opaque identity as one argument across the shell boundary.
$arguments=@('--map-frozen')
if($Check){$arguments+='--check'}
elseif($Receipt){$arguments+=@('--receipt',$Receipt)}
else{$arguments+=@('--freeze',$Freeze)}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) @arguments
exit $LASTEXITCODE
