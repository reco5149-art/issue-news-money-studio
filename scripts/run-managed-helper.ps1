function Invoke-StudioHelper {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [string[]]$ExtraArguments = @(),
        [Parameter(Mandatory=$true)][string]$LogPrefix,
        [int]$TimeoutSeconds = 180
    )
    # A native pipeline can retain handles inherited by windowless server children.
    # Wait for the helper itself, never its long-running descendants or pipe EOF.
    $helperArguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $ScriptPath + '"'
    if ($ExtraArguments.Count) { $helperArguments += ' ' + ($ExtraArguments -join ' ') }
    $helperProcess = Start-Process -FilePath 'powershell.exe' -ArgumentList $helperArguments `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput ($LogPrefix + '.stdout.log') `
        -RedirectStandardError ($LogPrefix + '.stderr.log')
    # Windows PowerShell 5.1 can otherwise lose ExitCode after a short process exits.
    $helperHandle = $helperProcess.Handle
    if (-not $helperProcess.WaitForExit($TimeoutSeconds * 1000)) {
        throw 'Managed helper did not exit in time; inspect its log before retrying.'
    }
    $helperProcess.Refresh()
    if ($helperProcess.ExitCode -ne 0) {
        throw ('Managed helper failed (exit ' + $helperProcess.ExitCode + '); inspect its log.')
    }
}
