# run_daily.ps1 - the actual scan invoked by the JobScoutDailyScan scheduled task.
# Not meant to be run interactively (use run_scan.bat for that) - no `pause`, and
# output goes to a dated log instead of the console since Task Scheduler runs headless.
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repo

$logDir = Join-Path $repo "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("scan_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] JobScoutDailyScan starting" | Out-File $log -Encoding utf8
python run.py *>> $log
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] JobScoutDailyScan finished (exit $LASTEXITCODE)" | Out-File $log -Append -Encoding utf8
