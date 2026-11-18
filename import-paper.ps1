<#
.SYNOPSIS
Imports a PDF with source coordinates, reviews an extraction, or runs W03 acceptance.
.PARAMETER Pdf
Local PDF path. The default input is the reviewed case_11 paper.
.PARAMETER Extraction
Saved extraction ID to reopen instead of importing a file.
.PARAMETER Page
One-based physical page to render, defaulting to the first page.
.PARAMETER Find
Exact extracted text to locate on Page and render as a source crop.
.PARAMETER Semantics
Extract source-cited case_11 model conditions, analysis methods and candidate goals.
.PARAMETER SemanticSnapshot
Reopen an immutable semantic draft from the local catalog.
.PARAMETER CheckSemantics
Run isolated semantic extraction and provenance acceptance.
.PARAMETER Check
Runs isolated acceptance including PDF geometry and database restoration.
.EXAMPLE
.\import-paper.ps1 -Page 4 -Find 'Schedulability Algorithm'
#>
[CmdletBinding(DefaultParameterSetName='Import')]
param(
    [Parameter(ParameterSetName='Import')][string]$Pdf,
    [Parameter(Mandatory,ParameterSetName='Show')][string]$Extraction,
    [Parameter(Mandatory,ParameterSetName='Check')][switch]$Check,
    [Parameter(Mandatory,ParameterSetName='SemanticShow')][string]$SemanticSnapshot,
    [Parameter(Mandatory,ParameterSetName='SemanticCheck')][switch]$CheckSemantics,
    [switch]$Semantics,
    [int]$Page=1,
    [string]$Find
)
$ErrorActionPreference='Stop'
# config identifies the project's WSL distribution; entry is the Linux launcher path.
$config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'configs/toolchain.json') -Raw | ConvertFrom-Json
$entry=& wsl.exe -d $config.distribution --exec wslpath -u (Join-Path $PSScriptRoot 'tools/w03_env.sh')
if($LASTEXITCODE -ne 0){throw 'Could not resolve the W03 launcher path.'}
 # arguments keeps each CLI token separate when passing through PowerShell and WSL.
$arguments=@('--page',"$Page")
if($Check){$arguments=@('--check')}
elseif($CheckSemantics){$arguments=@('--check-semantics')}
elseif($SemanticSnapshot){$arguments+=@('--semantic-snapshot',$SemanticSnapshot)}
elseif($Extraction){$arguments+=@('--show',$Extraction)}
elseif($Pdf){
    # Resolve the source before conversion so relative Windows paths keep their intended meaning.
    $resolved=(Resolve-Path -LiteralPath $Pdf).Path
    $linuxPdf=& wsl.exe -d $config.distribution --exec wslpath -u $resolved
    if($LASTEXITCODE -ne 0){throw 'Could not resolve the PDF path.'}
    $arguments+=@('--pdf',$linuxPdf.Trim())
}
if($Semantics){$arguments+=@('--semantics')}
if($Find){$arguments+=@('--find',$Find)}
& wsl.exe -d $config.distribution --exec bash ($entry.Trim()) @arguments
exit $LASTEXITCODE
