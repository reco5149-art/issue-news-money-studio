$ErrorActionPreference = 'Stop'
$studioRoot = Split-Path -Parent $PSScriptRoot
$studioWatch = Join-Path $PSScriptRoot 'watch-server.ps1'
$studioArguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $studioWatch + '"'
$studioAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $studioArguments -WorkingDirectory $studioRoot
$studioUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$studioTrigger = New-ScheduledTaskTrigger -AtLogOn -User $studioUser
$studioPrincipal = New-ScheduledTaskPrincipal -UserId $studioUser -LogonType Interactive -RunLevel Limited
$studioSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'IssueStudio-ServerWatchdog' -Action $studioAction -Trigger $studioTrigger -Principal $studioPrincipal -Settings $studioSettings -Description 'Start Issue Studio after login and recover an absent listener. stop.bat pauses recovery.' -Force | Out-Null
Start-ScheduledTask -TaskName 'IssueStudio-ServerWatchdog'
Write-Host 'Installed IssueStudio-ServerWatchdog. Starts after user login. stop.bat pauses; start.bat resumes.'
