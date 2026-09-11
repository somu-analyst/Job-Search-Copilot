# schedule_local_daily.ps1 - register/refresh the Windows scheduled task that runs
# run_daily.ps1 (-> python run.py) once a day. Idempotent: safe to re-run after
# changing -At. This machine must be on (and not asleep) at the scheduled time --
# same limitation as this project's existing ClaudeResume task.
#
# Usage:
#   .\schedule_local_daily.ps1                # register/refresh, default 07:00
#   .\schedule_local_daily.ps1 -At "06:30"     # custom daily time
#   .\schedule_local_daily.ps1 -Remove         # unregister
param(
    [string]$At = "07:00",
    [switch]$Remove
)

$TaskName = "JobScoutDailyScan"
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

if ($Remove) {
    Write-Host "Removed scheduled task '$TaskName'."
    exit 0
}

try {
    $when = [datetime]::ParseExact($At, "HH:mm", $null)
} catch {
    Write-Host "Could not parse -At '$At' - use 'HH:mm' (e.g. 07:00)"
    exit 1
}

$runner = Join-Path $repo "run_daily.ps1"
$arg = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $runner
$act = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$trg = New-ScheduledTaskTrigger -Daily -At $when

try {
    Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger $trg -Force | Out-Null
    Write-Host ("OK: '{0}' will run daily at {1}, logging to {2}\logs\" -f $TaskName, $when.ToString("HH:mm"), $repo)
    Write-Host "Run once now to test:  Start-ScheduledTask -TaskName $TaskName"
    Write-Host "Remove with:           .\schedule_local_daily.ps1 -Remove"
} catch {
    Write-Host ("Failed to register task: {0}" -f $_.Exception.Message)
    exit 1
}
