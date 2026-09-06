<#
.SYNOPSIS
    Create or update EvidenceOps Desktop shortcut to run the automated batch launcher.
#>

$repoRoot = Split-Path -Parent $PSScriptRoot
$batPath = Join-Path $repoRoot "EvidenceOps.bat"
$icoPath = Join-Path $repoRoot "scripts\EvidenceOps.ico"
$desktopLnk = "$env:USERPROFILE\Desktop\EvidenceOps.lnk"

$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut($desktopLnk)
$lnk.TargetPath = $batPath
$lnk.WorkingDirectory = $repoRoot
if (Test-Path $icoPath) {
    $lnk.IconLocation = "$icoPath,0"
}
$lnk.Description = "EvidenceOps Local-First Desktop App"
$lnk.Save()

Write-Host "EvidenceOps Desktop shortcut configured successfully: $desktopLnk" -ForegroundColor Green
