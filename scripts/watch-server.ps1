$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioData = Join-Path $studioRoot 'data'
$studioPause = Join-Path $studioData 'server.paused'
$studioLog = Join-Path $studioData 'watchdog.log'
. (Join-Path $PSScriptRoot 'run-managed-helper.ps1')
$studioNextMediaCheck = Get-Date
$studioLastMediaState = ''
$studioMutex = New-Object Threading.Mutex($false, 'Local\IssueStudioServerWatchdog')
try { $studioOwnsMutex = $studioMutex.WaitOne(0) }
catch [Threading.AbandonedMutexException] { $studioOwnsMutex = $true }
if (-not $studioOwnsMutex) { exit 0 }
Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Watchdog media-recovery-v2 started; PID $PID."
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class StudioPower {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
try {
    while ($true) {
        if (-not (Test-Path -LiteralPath $studioPause)) {
            try {
                $studioReply = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 10
                if ($null -eq $studioReply.connections) { throw 'Unexpected health response' }
                $studioPosts = Invoke-RestMethod 'http://127.0.0.1:8765/api/posts' -TimeoutSec 10
                if ($studioPosts.posts) { $studioPosts = $studioPosts.posts }
                $studioQueued = @($studioPosts | Where-Object { $_.status -in @('scheduled','publishing') })
                # Keep active production/delivery awake without changing the power plan.
                if ($studioQueued.Count -gt 0 -or $studioReply.autopilot.status -eq 'running') {
                    [StudioPower]::SetThreadExecutionState([uint32]2147483649) | Out-Null
                } else {
                    [StudioPower]::SetThreadExecutionState([uint32]2147483648) | Out-Null
                }
            } catch {
                # Never terminate a busy or unknown listener: slow generation is not a crash.
                $studioListener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
                if (-not $studioListener) {
                    Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Listener absent; starting server."
                    try {
                        Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'start.ps1') -ExtraArguments @('-NoBrowser') -LogPrefix (Join-Path $studioData 'watch-start')
                        Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Server start helper exited; health monitoring continues."
                    } catch {
                        Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Server start failed; inspect watch-start logs."
                    }
                }
            }
            # The editor health endpoint cannot detect a dead public media URL.
            if ((Get-Date) -ge $studioNextMediaCheck -and
                (Test-Path -LiteralPath (Join-Path $studioData 'public-media-url.txt')) -and
                -not (Test-Path -LiteralPath (Join-Path $studioData 'media.paused'))) {
                $studioNextMediaCheck = (Get-Date).AddMinutes(5)
                $studioMediaResult = & (Join-Path $studioRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'check_public_media.py')
                $studioMediaExit = $LASTEXITCODE
                $studioMediaState = if ($studioMediaExit -eq 0) { 'healthy' } else { 'unavailable' }
                if ($studioMediaState -ne $studioLastMediaState) {
                    Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Public image $studioMediaState (check exit $studioMediaExit)."
                    $studioLastMediaState = $studioMediaState
                }
                if ($studioMediaExit -ne 0) {
                    & (Join-Path $studioRoot '.venv\Scripts\python.exe') -X utf8 (Join-Path $PSScriptRoot 'check_public_media.py') --can-restart | Out-Null
                    if ($LASTEXITCODE -eq 0) {
                        Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Public image unavailable; repairing managed media service."
                        try {
                            Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'start-public-media.ps1') -ExtraArguments @('-Automatic') -LogPrefix (Join-Path $studioData 'watch-media')
                            Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Media recovery helper exited; health monitoring continues."
                        } catch {
                            Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Media recovery deferred or failed; next health check in five minutes."
                        }
                    } else {
                        Add-Content -LiteralPath $studioLog -Encoding UTF8 -Value "$(Get-Date -Format o) Media recovery deferred: active work, imminent reservation or unavailable status."
                    }
                }
            }
        } else { [StudioPower]::SetThreadExecutionState([uint32]2147483648) | Out-Null }
        Start-Sleep -Seconds 30
    }
} finally {
    [StudioPower]::SetThreadExecutionState([uint32]2147483648) | Out-Null
    $studioMutex.ReleaseMutex(); $studioMutex.Dispose()
}
