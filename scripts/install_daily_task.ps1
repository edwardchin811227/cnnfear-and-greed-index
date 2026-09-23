param(
  [string]$TaskName = "cnnfng-auto-sync",
  [string]$RunAt = "08:10",
  [bool]$RunOnStartup = $false,
  [bool]$RunOnLogon = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RunAt -notmatch "^(?:[01]\d|2[0-3]):[0-5]\d$") {
  throw "RunAt must be HH:mm (24-hour), e.g. 08:10"
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runScript = Join-Path $repo "scripts\run_daily.ps1"
if (-not (Test-Path -LiteralPath $runScript)) {
  throw "Missing script: $runScript"
}

$arg = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -Push -BackfillDays 10"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$parts = $RunAt.Split(":")
$at = Get-Date -Hour ([int]$parts[0]) -Minute ([int]$parts[1]) -Second 0
$triggers = @()
$triggers += New-ScheduledTaskTrigger -Daily -At $at
if ($RunOnStartup) {
  $triggers += New-ScheduledTaskTrigger -AtStartup
}
if ($RunOnLogon) {
  $triggers += New-ScheduledTaskTrigger -AtLogOn
}
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null

Write-Output ""
Write-Output "Task configured:"
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State, TaskPath | Out-String | Write-Output
Get-ScheduledTask -TaskName $TaskName | Select-Object -ExpandProperty Triggers | Format-Table -AutoSize | Out-String | Write-Output
Get-ScheduledTaskInfo -TaskName $TaskName | Format-List LastRunTime, LastTaskResult, NextRunTime | Out-String | Write-Output
