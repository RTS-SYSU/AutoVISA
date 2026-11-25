<#
.SYNOPSIS
Starts the AutoVISA workspace and its local OpenAI connection.
.PARAMETER Port
Local port, separate from the real workbench service.
.EXAMPLE
.\start-prototype.ps1
#>
[CmdletBinding()]
param([ValidateRange(1,65535)][int]$Port = 8769)
# The loopback server hosts both the workspace and its model settings.
$prototypeEntry = Join-Path $PSScriptRoot 'tools/serve-prototype.cjs'
& node $prototypeEntry --port $Port
