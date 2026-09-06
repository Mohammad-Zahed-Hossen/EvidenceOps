<#
.SYNOPSIS
    EvidenceOps Desktop Application Lifecycle Launcher
.DESCRIPTION
    Automates local background service startup (Docker Qdrant, Ollama, FastAPI server),
    launches the EvidenceOps dashboard in dedicated browser app mode, ensures desktop
    shortcuts point to the automated launcher, and cleanly stops all background services
    and unloads models upon window close to reclaim system RAM.
#>

[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           EvidenceOps Desktop Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 0. Sync Desktop and Start Menu Shortcuts
$desktopLnk = "$env:USERPROFILE\Desktop\EvidenceOps.lnk"
$braveAppsLnk = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Brave Apps\EvidenceOps.lnk"
$batPath = Join-Path $repoRoot "EvidenceOps.bat"
$icoPath = Join-Path $repoRoot "scripts\EvidenceOps.ico"

try {
    $sh = New-Object -ComObject WScript.Shell
    foreach ($sc in @($desktopLnk, $braveAppsLnk)) {
        if (Test-Path $sc) {
            $lnk = $sh.CreateShortcut($sc)
            if ($lnk.TargetPath -ne $batPath) {
                $lnk.TargetPath = $batPath
                $lnk.WorkingDirectory = $repoRoot
                if (Test-Path $icoPath) {
                    $lnk.IconLocation = "$icoPath,0"
                }
                $lnk.Description = "EvidenceOps Local-First Desktop App"
                $lnk.Save()
                Write-Host "  -> Desktop shortcut synced with automated launcher" -ForegroundColor Gray
            }
        }
    }
} catch {
    # Non-fatal if shortcut cannot be written
}

# 1. Start Qdrant Docker Container
Write-Host "`n[1/4] Starting local Qdrant vector database..." -ForegroundColor Yellow
$dockerPing = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  -> Docker Desktop daemon is not running. Attempting to start Docker Desktop..." -ForegroundColor Gray
    $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process $dockerExe
        Write-Host "  -> Waiting up to 25 seconds for Docker Desktop engine to initialize..." -ForegroundColor Gray
        for ($w = 0; $w -lt 25; $w++) {
            Start-Sleep -Seconds 1
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                break
            }
        }
    }
}

docker compose up -d qdrant 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  -> Qdrant container is active (127.0.0.1:6333)" -ForegroundColor Green
} else {
    Write-Warning "Docker Desktop could not be reached. Open Docker Desktop from the Start Menu, then click Refresh on the dashboard."
}

# 2. Check / Start Ollama
Write-Host "`n[2/4] Checking local Ollama engine..." -ForegroundColor Yellow
$ollamaRunning = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaRunning) {
    Write-Host "  -> Launching background Ollama process..." -ForegroundColor Gray
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
} else {
    Write-Host "  -> Ollama service is already running" -ForegroundColor Green
}

# 3. Start EvidenceOps FastAPI Backend
Write-Host "`n[3/4] Starting EvidenceOps local API & dashboard server (127.0.0.1:8080)..." -ForegroundColor Yellow
$serverProcess = Start-Process "uv" `
    -ArgumentList "run uvicorn evidenceops.api.app:create_app --factory --host 127.0.0.1 --port 8080" `
    -PassThru `
    -WindowStyle Hidden

# 4. Wait for Server Health Probe
Write-Host "`n[4/4] Waiting for application readiness..." -ForegroundColor Yellow
$ready = $false
$maxWaitSeconds = 20
$startTime = Get-Date

while (((Get-Date) - $startTime).TotalSeconds -lt $maxWaitSeconds) {
    Start-Sleep -Milliseconds 800
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($resp.status -eq "ready" -or $resp.status -eq "degraded") {
            $ready = $true
            break
        }
    } catch {
        # Server still starting
    }
}

if ($ready) {
    Write-Host "  -> EvidenceOps service is ready!" -ForegroundColor Green
} else {
    Write-Warning "Service startup took longer than expected. Opening dashboard anyway..."
}

# 5. Detect Best Browser (Brave, Chrome, Edge)
$appUrl = "http://127.0.0.1:8080/"
$profileDir = "$env:LOCALAPPDATA\EvidenceOps\browser_profile"
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}

$browserCandidates = @(
    "$env:LocalAppData\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
)

$selectedBrowser = $null
foreach ($cand in $browserCandidates) {
    if (Test-Path $cand) {
        $selectedBrowser = $cand
        break
    }
}

$appProcess = $null
try {
    if ($selectedBrowser) {
        # Using a dedicated profile directory prevents the process from exiting immediately
        # by delegating to an existing browser instance, ensuring clean lifecycle tracking.
        $browserArgs = @(
            "--user-data-dir=$profileDir",
            "--app=$appUrl",
            "--window-size=1280,850"
        )
        $appProcess = Start-Process -FilePath $selectedBrowser -ArgumentList $browserArgs -PassThru
    } else {
        Start-Process $appUrl
    }

    Write-Host "`n============================================================" -ForegroundColor Cyan
    Write-Host "  [ACTIVE] EvidenceOps Desktop App is Running" -ForegroundColor Green
    Write-Host "  URL: $appUrl" -ForegroundColor Cyan
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host "  To stop the app and free all RAM:" -ForegroundColor White
    Write-Host "    - Close the EvidenceOps window, OR" -ForegroundColor Gray
    Write-Host "    - Press [ENTER] or [Q] in this window" -ForegroundColor Gray
    Write-Host "============================================================" -ForegroundColor Cyan

    # 6. Monitor Window and Console for Clean Termination
    while ($appProcess -and -not $appProcess.HasExited) {
        if ([Console]::IsInputRedirected -eq $false -and [Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Enter -or $key.Key -eq [ConsoleKey]::Q) {
                Write-Host "`nShutdown initiated by user..." -ForegroundColor Yellow
                break
            }
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $appProcess) {
        Read-Host "`nBrowser opened. Press ENTER when finished to stop background services..."
    }
} finally {
    # 7. Automatic Clean Shutdown & Memory Reclaim
    Write-Host "`n============================================================" -ForegroundColor Magenta
    Write-Host "       Closing EvidenceOps & Reclaiming RAM" -ForegroundColor Magenta
    Write-Host "============================================================" -ForegroundColor Magenta

    # Close Browser Window if still running
    if ($appProcess -and -not $appProcess.HasExited) {
        Write-Host "Closing EvidenceOps window..." -ForegroundColor Gray
        Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
    }

    # Stop FastAPI Server Process
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Write-Host "Stopping FastAPI backend (PID: $($serverProcess.Id))..." -ForegroundColor Gray
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }

    # Stop Qdrant Container
    Write-Host "Stopping Qdrant container..." -ForegroundColor Gray
    docker compose stop qdrant 2>$null | Out-Null

    # Unload Model from Ollama RAM/VRAM
    $envFile = Join-Path $repoRoot ".env"
    $model = "qwen2.5:1.5b"
    if (Test-Path $envFile) {
        $match = Get-Content $envFile | Where-Object { $_ -match "^OLLAMA_MODEL=(.+)$" }
        if ($match) {
            $model = $matches[1].Trim()
        }
    }
    Write-Host "Unloading Ollama model ($model) from memory..." -ForegroundColor Gray
    ollama stop $model 2>$null | Out-Null

    Write-Host "`nAll background processes stopped. Memory reclaimed successfully!" -ForegroundColor Green
    Start-Sleep -Seconds 2
}
