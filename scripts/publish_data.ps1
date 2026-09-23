param(
  [switch]$Push
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$csvRel = "data/fng.csv"
$jsonRel = "docs/fng_data.json"
$csvAbs = Join-Path $repo "data\fng.csv"
$jsonAbs = Join-Path $repo "docs\fng_data.json"

if (-not (Test-Path -LiteralPath $csvAbs)) {
  throw "Missing file: $csvAbs"
}
if (-not (Test-Path -LiteralPath $jsonAbs)) {
  throw "Missing file: $jsonAbs"
}

git -C $repo add -- $csvRel $jsonRel
git -C $repo diff --cached --quiet -- $csvRel $jsonRel
if ($LASTEXITCODE -eq 0) {
  Write-Output "No data changes to commit."
  exit 0
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$msg = "data: update fng $ts"
git -C $repo commit -m $msg -- $csvRel $jsonRel
if ($LASTEXITCODE -ne 0) {
  throw "git commit failed with exit code $LASTEXITCODE"
}

if ($Push) {
  git -C $repo push origin main
  if ($LASTEXITCODE -ne 0) {
    throw "git push failed with exit code $LASTEXITCODE"
  }
  Write-Output "Pushed to origin/main."
} else {
  Write-Output "Committed locally. Re-run with -Push to publish."
}
