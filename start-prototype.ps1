<#
.SYNOPSIS
Starts the isolated clickable UI prototype on loopback.
.PARAMETER Port
Local port, separate from the real workbench service.
.EXAMPLE
.\start-prototype.ps1
#>
[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port = 8769)
# prototypeEntry points to the local static server; no backend is started.
$prototypeEntry = Join-Path $PSScriptRoot 'tools/serve-prototype.cjs'
& node $prototypeEntry --port $Port
