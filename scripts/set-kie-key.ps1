# KIE AI 키를 .env와 data\external-api-keys.env에 저장하고, 인증 확인 후 서버를 재시작합니다.
# 키 값은 화면·로그에 출력하지 않습니다.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Set-KieKey([string]$path, [string]$key) {
    $text = ''
    if (Test-Path -LiteralPath $path) { $text = [IO.File]::ReadAllText($path, $utf8) }
    $line = "KIE_API_KEY=$key"
    $m = [regex]::Match($text, '(?m)^KIE_API_KEY=[^\r\n]*')
    if ($m.Success) {
        $text = $text.Substring(0, $m.Index) + $line + $text.Substring($m.Index + $m.Length)
    } else {
        if ($text.Length -gt 0 -and -not $text.EndsWith("`n")) { $text += "`r`n" }
        $text += "$line`r`n"
    }
    [IO.File]::WriteAllText($path, $text, $utf8)
}

try {
    Write-Host ''
    Write-Host '=== KIE AI 키 연결 ===' -ForegroundColor Cyan
    Write-Host 'KIE AI 사이트에서 복사한 API 키를 붙여넣고 Enter를 누르세요.'
    Write-Host '(Ctrl+V 또는 마우스 오른쪽 클릭으로 붙여넣기. 보안을 위해 화면에 글자가 보이지 않습니다.)'
    $secure = Read-Host -AsSecureString 'API 키'
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($key -notmatch '^[^\s"''#=]{16,300}$') {
        throw '키 형식이 올바르지 않습니다. 따옴표나 공백 없이 키만 다시 붙여넣어 주세요. 파일은 바꾸지 않았습니다.'
    }

    $envFile = Join-Path $root '.env'
    $dataDir = Join-Path $root 'data'
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    if (Test-Path -LiteralPath $envFile) {
        # data\ 폴더는 Git에서 제외되므로 백업이 GitHub에 올라가지 않습니다.
        Copy-Item -LiteralPath $envFile -Destination (Join-Path $dataDir ('env-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.env'))
    }
    Set-KieKey $envFile $key
    $extra = Join-Path $dataDir 'external-api-keys.env'
    if (Test-Path -LiteralPath $extra) { Set-KieKey $extra $key }
    $key = $null
    Write-Host '[1/3] 키를 저장했습니다.' -ForegroundColor Green

    Write-Host '[2/3] KIE AI 인증을 확인합니다. (이미지 생성·과금 없음)'
    $py = Join-Path $root '.venv\Scripts\python.exe'
    # Windows PowerShell 5.1 can turn native stderr into a terminating error under 'Stop'.
    $ErrorActionPreference = 'Continue'
    $out = & $py (Join-Path $PSScriptRoot 'check_media_connections.py') 2>$null
    $ErrorActionPreference = 'Stop'
    $kie = $null
    try { $kie = ($out | Out-String | ConvertFrom-Json).results | Where-Object { $_.service -eq 'KIE AI' } } catch {}
    if ($kie -and $kie.authenticated) {
        $credit = if ($null -ne $kie.credits) { " / 남은 크레딧: $($kie.credits)" } else { '' }
        Write-Host "      인증 성공$credit" -ForegroundColor Green
    } else {
        $why = if ($kie) { "$($kie.error) $($kie.http_status)" } else { '응답 확인 불가' }
        Write-Host "      인증 실패 ($why). 키를 다시 확인한 뒤 이 파일을 다시 실행하세요." -ForegroundColor Red
    }

    Write-Host '[3/3] 새 설정을 적용하려고 서버를 다시 시작합니다.'
    & (Join-Path $PSScriptRoot 'stop.ps1') | Out-Host
    Start-Sleep -Seconds 2
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/status' -TimeoutSec 2 | Out-Null
        Write-Host '      기존 서버가 아직 실행 중입니다. stop.bat으로 멈출 수 없는 방식으로 켜진 서버일 수 있습니다.' -ForegroundColor Yellow
        Write-Host '      그 서버 창을 닫거나 PC를 재시작한 뒤 start.bat을 실행하세요.' -ForegroundColor Yellow
    } catch {
        & (Join-Path $PSScriptRoot 'start.ps1') -NoBrowser | Out-Host
    }
    Write-Host ''
    Write-Host '완료되었습니다. 이 창은 닫아도 됩니다.' -ForegroundColor Cyan
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
