param(
  [switch]$Push,
  [int]$BackfillDays = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($BackfillDays -lt 0) {
  throw "BackfillDays must be >= 0"
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$updateScript = Join-Path $repo "scripts\fetch_and_process.py"
$publishScript = Join-Path $repo "scripts\publish_data.ps1"

if (-not (Test-Path -LiteralPath $updateScript)) {
  throw "Missing script: $updateScript"
}
if (-not (Test-Path -LiteralPath $publishScript)) {
  throw "Missing script: $publishScript"
}

Write-Output "run_at_local=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Output "backfill_days=$BackfillDays"

$output = & python $updateScript --backfill-days $BackfillDays 2>&1
$exitCode = $LASTEXITCODE
$output | ForEach-Object { Write-Output $_ }
if ($exitCode -ne 0) {
  throw "fetch_and_process.py failed with exit code $exitCode"
}

$targetLine = $output | Where-Object { "$_" -like "target_date=*" } | Select-Object -Last 1
if (-not $targetLine) {
  throw "Cannot determine target_date from fetch_and_process.py output"
}

if ($Push) {
  & $publishScript -Push
} else {
  & $publishScript
}
