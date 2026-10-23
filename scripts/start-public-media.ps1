param([switch]$Automatic)
$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioData = Join-Path $studioRoot 'data'
. (Join-Path $PSScriptRoot 'run-managed-helper.ps1')
$mediaPause = Join-Path $studioData 'media.paused'
$mediaPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
$mediaCheck = Join-Path $PSScriptRoot 'check_public_media.py'
$mediaMutex = New-Object Threading.Mutex($false, 'Local\IssueStudioPublicMedia')
try { $mediaOwnsMutex = $mediaMutex.WaitOne(0) }
catch [Threading.AbandonedMutexException] { $mediaOwnsMutex = $true }
if (-not $mediaOwnsMutex) { exit 0 }
try {
if ($Automatic -and (Test-Path -LiteralPath $mediaPause)) { exit 0 }
if (-not $Automatic -and (Test-Path -LiteralPath $mediaPause)) { Remove-Item -LiteralPath $mediaPause }
$cfExe = Join-Path $studioData 'tools\cloudflared.exe'
if (-not (Test-Path -LiteralPath $cfExe)) { throw 'cloudflared is missing from data/tools.' }
$tunnelPidFile = Join-Path $studioData 'media-tunnel.pid'
if (Test-Path -LiteralPath $tunnelPidFile) {
    $existing = Get-Process -Id ([int](Get-Content -LiteralPath $tunnelPidFile)) -ErrorAction SilentlyContinue
    if ($existing -and $existing.Path -eq $cfExe) {
        $savedUrl = (Get-Content -LiteralPath (Join-Path $studioData 'public-media-url.txt') -Raw).Trim()
        $healthy = $false
        try {
            if ($savedUrl -match '^https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com$') {
                & $mediaPython -X utf8 $mediaCheck | Out-Null
                $healthy = ($LASTEXITCODE -eq 0)
            }
        } catch { $healthy = $false }
        if ($healthy) {
            Write-Host 'Public media is already running.'
            Write-Host $savedUrl
            exit 0
        }
        if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
            & $mediaPython -X utf8 $mediaCheck --can-restart | Out-Null
            if ($LASTEXITCODE -ne 0) { throw 'Recovery deferred: active work or an imminent reservation must finish first.' }
        }
        Stop-Process -Id $existing.Id

    }
}
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    & $mediaPython -X utf8 $mediaCheck --can-restart | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Recovery deferred: active work or an imminent reservation must finish first.' }
}
$listener = Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    if ($owner.CommandLine -notmatch 'uvicorn app\.media_server:app') { throw 'Port 8766 is used by another program.' }
} else {
    Start-Process -FilePath (Join-Path $studioRoot '.venv\Scripts\pythonw.exe') -ArgumentList '-m','uvicorn','app.media_server:app','--host','127.0.0.1','--port','8766' -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioData 'media.stdout.log') -RedirectStandardError (Join-Path $studioData 'media.stderr.log') | Out-Null
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        $listener = Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $listener) { throw 'Media server did not start.' }
}
$listener[0].OwningProcess | Set-Content -LiteralPath (Join-Path $studioData 'media.pid')
$cfLog = Join-Path $studioData 'media-tunnel.stderr.log'
$cfProcess = Start-Process -FilePath $cfExe -ArgumentList 'tunnel','--url','http://127.0.0.1:8766','--no-autoupdate','--protocol','http2' -WorkingDirectory $studioRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $studioData 'media-tunnel.stdout.log') -RedirectStandardError $cfLog
$cfProcess.Id | Set-Content -LiteralPath $tunnelPidFile
$publicUrl = $null
for ($attempt=0; $attempt -lt 50; $attempt++) {
    Start-Sleep -Milliseconds 500
    $logText = Get-Content -LiteralPath $cfLog -Raw -ErrorAction SilentlyContinue
    $urlMatch = [regex]::Match([string]$logText, 'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com')
    if ($urlMatch.Success) { $publicUrl = $urlMatch.Value; break }
    $cfProcess.Refresh()
    if ($cfProcess.HasExited) { throw 'Tunnel startup failed. See data/media-tunnel.stderr.log.' }
}
if (-not $publicUrl) { throw 'Public URL was not assigned. See data/media-tunnel.stderr.log.' }
$mediaReady = $false
for ($attempt=0; $attempt -lt 6; $attempt++) {
    & $mediaPython -X utf8 $mediaCheck --base-url $publicUrl | Out-Null
    if ($LASTEXITCODE -eq 0) { $mediaReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $mediaReady) { throw 'New tunnel did not serve the exact local image; application URL was not changed.' }
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    & $mediaPython -X utf8 $mediaCheck --can-restart | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Recovery deferred before configuration change: active work or an imminent reservation.' }
}
$envFile = Join-Path $studioRoot '.env'
$envText = [IO.File]::ReadAllText($envFile)
$line = 'PUBLIC_MEDIA_BASE_URL=' + $publicUrl
if ($envText -match '(?m)^PUBLIC_MEDIA_BASE_URL=') { $envText = [regex]::Replace($envText, '(?m)^PUBLIC_MEDIA_BASE_URL=.*', $line) }
else { $envText += "`n$line`n" }
[IO.File]::WriteAllText($envFile, $envText, (New-Object Text.UTF8Encoding($false)))
$publicUrl | Set-Content -LiteralPath (Join-Path $studioData 'public-media-url.txt')
Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'stop.ps1') -LogPrefix (Join-Path $studioData 'media-editor-stop')
Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'start.ps1') -ExtraArguments @('-NoBrowser') -LogPrefix (Join-Path $studioData 'media-editor-start')
Write-Host "Public images: $publicUrl"
Write-Host 'Temporary demo address. Keep the PC running. Restarting the tunnel changes the address.'
} finally {
    $mediaMutex.ReleaseMutex()
    $mediaMutex.Dispose()
}
