param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioUrl = 'http://127.0.0.1:8765'
$studioData = Join-Path $studioRoot 'data'
New-Item -ItemType Directory -Path $studioData -Force | Out-Null

function Test-StudioHealth {
    try {
        $reply = Invoke-RestMethod -Uri "$studioUrl/api/status" -TimeoutSec 2
        return ($null -ne $reply.connections -and $null -ne $reply.daily)
    } catch { return $false }
}

try {
    $studioPause = Join-Path $studioData 'server.paused'
    if (Test-Path -LiteralPath $studioPause) { Remove-Item -LiteralPath $studioPause }
    if (Test-StudioHealth) {
        Write-Host "Issue Studio is already running: $studioUrl"
        if (-not $NoBrowser) { Start-Process $studioUrl }
        exit 0
    }
    if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8765 is used by another program. The existing process was not stopped.'
    }
    $studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $studioPython)) {
        & python -m venv (Join-Path $studioRoot '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or newer, then run start.bat again.' }
    }
    & $studioPython (Join-Path $PSScriptRoot 'check_dependencies.py')
    if ($LASTEXITCODE -ne 0) {
        & $studioPython -m pip install -r (Join-Path $studioRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network and retry.' }
    }
    $studioPythonWindowless = Join-Path $studioRoot '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $studioPythonWindowless)) { $studioPythonWindowless = $studioPython }
    $studioStarted = Start-Process -FilePath $studioPythonWindowless `
        -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8765' `
        -WorkingDirectory $studioRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $studioData 'server.stdout.log') `
        -RedirectStandardError (Join-Path $studioData 'server.stderr.log')
    $studioReady = $false
    for ($studioAttempt = 0; $studioAttempt -lt 30; $studioAttempt++) {
        if (Test-StudioHealth) { $studioReady = $true; break }
        $studioStarted.Refresh()
        if ($studioStarted.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $studioReady) {
        throw "Server did not start. See $studioData\server.stderr.log"
    }
    # Windows venv pythonw starts a child interpreter. Record the actual listener,
    # so stop.bat stops the server rather than only its launcher.
    $studioListener = Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object -First 1
    $studioListener.OwningProcess | Set-Content -LiteralPath (Join-Path $studioData 'server.pid') -Encoding Ascii
    Write-Host "Issue Studio is running in the background: $studioUrl"
    Write-Host 'This window can be closed. To stop the app, run stop.bat.'
    if (-not $NoBrowser) { Start-Process $studioUrl }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
