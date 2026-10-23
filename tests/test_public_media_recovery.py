from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import pytest
from scripts.check_public_media import restart_safe, verify_bytes


NOW = datetime(2026, 10, 20, 15, tzinfo=timezone(timedelta(hours=9)))


def test_public_image_check_rejects_error_pages_and_different_bytes():
    assert verify_bytes(b"image", "image/jpeg", b"image")
    assert not verify_bytes(b"image", "text/html", b"image")
    assert not verify_bytes(b"other", "image/jpeg", b"image")


def test_recovery_waits_for_running_or_uncertain_work():
    assert not restart_safe({"autopilot": {"status": "running"}}, [], NOW)
    assert not restart_safe({"autopilot": {"status": "ready"}}, [], NOW)
    for phase in ("publishing", "needs_check"):
        assert not restart_safe({"autopilot": {"status": "waiting"}}, [{"status": phase}], NOW)


def test_recovery_does_not_race_due_production_or_publication():
    for offset in (-1, 0, 1, 2):
        due = (NOW + timedelta(minutes=offset)).isoformat()
        assert not restart_safe({"autopilot": {"status": "waiting", "next_retry_at": due}}, [], NOW)
        assert not restart_safe({"autopilot": {"status": "waiting"}}, [{"status": "scheduled", "scheduled_at": due}], NOW)
    assert restart_safe({"autopilot": {"status": "waiting", "next_retry_at": (NOW+timedelta(minutes=30)).isoformat()}}, [], NOW)


@pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell process-handle regression')
def test_helper_returns_without_waiting_for_server_descendant(tmp_path):
    helper = Path(__file__).resolve().parents[1] / 'scripts/run-managed-helper.ps1'
    (tmp_path/'child.ps1').write_text('Start-Sleep -Seconds 10', encoding='utf-8-sig')
    (tmp_path/'parent.ps1').write_text('''
$child = Join-Path $PSScriptRoot 'child.ps1'
Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $child + '"') -WindowStyle Hidden | Out-Null
exit 0
''', encoding='utf-8-sig')
    (tmp_path/'failure.ps1').write_text('exit 7', encoding='utf-8-sig')
    (tmp_path/'runner.ps1').write_text(". '" + str(helper).replace("'", "''") + "'\n" + '''
Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'parent.ps1') -LogPrefix (Join-Path $PSScriptRoot 'success') -TimeoutSeconds 4
try {
 Invoke-StudioHelper -ScriptPath (Join-Path $PSScriptRoot 'failure.ps1') -LogPrefix (Join-Path $PSScriptRoot 'failure')
 exit 1
} catch {
 if ($_.Exception.Message -notmatch 'exit 7') { throw }
}
''', encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(tmp_path/'runner.ps1')], capture_output=True, timeout=8)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
