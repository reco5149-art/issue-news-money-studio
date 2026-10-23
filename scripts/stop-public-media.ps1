$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
Set-Content -LiteralPath (Join-Path $studioRoot 'data\media.paused') -Value (Get-Date -Format o)
foreach ($name in @('media-tunnel','media')) {
    $pidFile = Join-Path $studioRoot "data\$name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $processId = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if ($process) {
        $expected = if ($name -eq 'media') { 'uvicorn app\.media_server:app' } else { 'cloudflared.*tunnel.*127\.0\.0\.1:8766' }
        if ($process.CommandLine -notmatch $expected) { throw 'Process identity mismatch; no process was stopped.' }
        Stop-Process -Id $processId
    }
    Remove-Item -LiteralPath $pidFile
}
Write-Host 'Public image access stopped.'
