<#
.SYNOPSIS
  Creates (or updates) the Windows Task Scheduler jobs StillOpen's emails need. Run once, from PowerShell.

.DESCRIPTION
  Nothing here is needed to use the app: the job search runs by itself when someone opens their dashboard. These tasks
  are for the emails, which only go out where SMTP is configured (EMAIL_HOST) and the switch is on in Site configuration.

  Tasks (all run under your own account, whether or not you are logged in only if you pass -Password; otherwise only while logged in):
    StillOpen interview reminders   every hour
    StillOpen follow-up emails      every day 08:00
    StillOpen job alerts            every day 07:00
    StillOpen refresh sources       every Sunday 03:00
    StillOpen refresh job board     every 6 hours

.EXAMPLE
  .\deploy\windows\schedule-stillopen.ps1
  .\deploy\windows\schedule-stillopen.ps1 -Remove
#>
param(
    [string]$AppDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Python = "",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
if (-not $Python) { $Python = Join-Path $AppDir ".venv\Scripts\python.exe" }
$names = @("StillOpen interview reminders", "StillOpen follow-up emails", "StillOpen job alerts", "StillOpen refresh sources", "StillOpen refresh job board")

if ($Remove) {
    foreach ($n in $names) { Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue; Write-Host "Removed $n" }
    return
}

if (-not (Test-Path $Python)) { throw "Python not found at $Python. Pass -Python <path to python.exe>." }
if (-not (Test-Path (Join-Path $AppDir "manage.py"))) { throw "manage.py not found in $AppDir. Pass -AppDir <folder with manage.py>." }
New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "logs") | Out-Null

function New-StillOpenTask($name, $command, $trigger) {
    $log = Join-Path $AppDir "logs\cron.log"
    $arg = "/c cd /d `"$AppDir`" && `"$Python`" manage.py $command >> `"$log`" 2>&1"
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled: $name  ->  manage.py $command"
}

$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
New-StillOpenTask "StillOpen interview reminders" "send_interview_reminders" $hourly
New-StillOpenTask "StillOpen follow-up emails" "send_followup_emails" (New-ScheduledTaskTrigger -Daily -At 8:00am)
New-StillOpenTask "StillOpen job alerts" "scheduled_scan" (New-ScheduledTaskTrigger -Daily -At 7:00am)
New-StillOpenTask "StillOpen refresh sources" "seed_sources" (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00am)
$sixHourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(15) -RepetitionInterval (New-TimeSpan -Hours 6)
New-StillOpenTask "StillOpen refresh job board" "refresh_postings" $sixHourly

Write-Host ""
Write-Host "Done. Output is appended to $AppDir\logs\cron.log. Remove them all with:  .\deploy\windows\schedule-stillopen.ps1 -Remove"
