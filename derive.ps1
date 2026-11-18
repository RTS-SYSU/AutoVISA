<#
.SYNOPSIS
Runs local bidirectional derivation and checks its exact proof obligations.
.PARAMETER Mapping
Checked W03 mapping receipt to use as immutable mathematical input.
.PARAMETER Run
Existing derivation execution to reopen and export.
#>
[CmdletBinding(DefaultParameterSetName='Mapping')]
param(
    [Parameter(Mandatory,ParameterSetName='Mapping')][string]$Mapping,
    [Parameter(Mandatory,ParameterSetName='Run')][string]$Run
)
$ErrorActionPreference='Stop'
# config identifies the installed WSL distribution and project-local runtime launcher.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve derivation launcher.'}
# arguments keeps opaque identities separate from executable shell syntax.
$arguments=@('--derive')
if($Run){$arguments+=@('--run',$Run)}
else{$arguments+=@('--mapping',$Mapping)}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) @arguments
exit $LASTEXITCODE
