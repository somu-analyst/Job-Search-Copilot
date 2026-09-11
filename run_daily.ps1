# run_daily.ps1 - the JobScoutDailyScan scheduled task's entrypoint.
# The Oracle VM now owns the actual scan (deploy/jobscout-scan.timer, 10:00 UTC ~
# 06:00 America/New_York) -- running a second independent scan here would double-
# spend the free-tier API quotas and let the two DBs drift apart. This just pulls
# whatever the VM found (sync_from_cloud.py is a MERGE: local status edits like
# "applied" are never overwritten, only new jobs/companies are added).
#
# For an actual local scan (e.g. the VM is down), scan_now.bat still does that.
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$logDir = Join-Path $repo "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("sync_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] JobScoutDailyScan (cloud sync) starting" | Out-File $log -Encoding utf8
python sync_from_cloud.py *>> $log
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] JobScoutDailyScan (cloud sync) finished (exit $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
