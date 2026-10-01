$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioData = Join-Path $studioRoot 'data'
$studioPause = Join-Path $studioData 'server.paused'
$studioLog = Join-Path $studioData 'watchdog.log'
$studioMutex = New-Object Threading.Mutex($false, 'Local\IssueStudioServerWatchdog')
try { $studioOwnsMutex = $studioMutex.WaitOne(0) }
catch [Threading.AbandonedMutexException] { $studioOwnsMutex = $true }
if (-not $studioOwnsMutex) { exit 0 }
try {
    while ($true) {
        if (-not (Test-Path -LiteralPath $studioPause)) {
            try {
                $studioReply = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 10
                if ($null -eq $studioReply.connections) { throw 'Unexpected health response' }
            } catch {
                # Never terminate a busy or unknown listener: slow generation is not a crash.
                $studioListener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
                if (-not $studioListener) {
                    Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Listener absent; starting server."
                    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start.ps1') -NoBrowser 2>&1 | Out-File -LiteralPath $studioLog -Append -Encoding UTF8
                }
            }
        }
        Start-Sleep -Seconds 30
    }
} finally { $studioMutex.ReleaseMutex(); $studioMutex.Dispose() }
