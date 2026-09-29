$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioPidFile = Join-Path $studioRoot 'data\server.pid'
try {
    if (-not (Test-Path -LiteralPath $studioPidFile)) {
        Write-Host 'No managed server PID was found.'
        exit 0
    }
    $studioProcessId = [int](Get-Content -LiteralPath $studioPidFile -Raw).Trim()
    $studioProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $studioProcessId"
    if ($studioProcess) {
        if ($studioProcess.CommandLine -notmatch 'uvicorn app\.main:app --host 127\.0\.0\.1 --port 8765') {
            throw 'PID belongs to a different process. It was not stopped.'
        }
        Stop-Process -Id $studioProcessId
    }
    Remove-Item -LiteralPath $studioPidFile
    Write-Host 'Issue Studio stopped. Run start.bat to start again.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
