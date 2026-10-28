<#
Update a StillOpen install to the latest code (Windows PowerShell 5.1 or 7).
  deploy\update.ps1              Docker Compose install (docker-compose.selfhost.yml), the default when docker is found
  deploy\update.ps1 -Source      Python install: pip install, migrate, build the app; you restart the server yourself
  deploy\update.ps1 -DryRun      only print what would be done
  deploy\update.ps1 -Yes         do not ask first
Refuses to run when you have uncommitted changes. Back up first: docs/SELF-HOSTING.md
#>
param([switch]$Source, [switch]$DryRun, [switch]$Yes)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$composeFile = "docker-compose.selfhost.yml"

if (git status --porcelain) {
    Write-Error "You have uncommitted changes. Commit or stash them first, then run this again."
    git status --short
    exit 1
}

$useDocker = (-not $Source) -and (Get-Command docker -ErrorAction SilentlyContinue) -and (Test-Path $composeFile)
if ($useDocker) {
    $steps = @("git pull --ff-only", "docker compose -f $composeFile up -d --build   # migrations run on start")
} else {
    $steps = @("git pull --ff-only", "python -m pip install -r requirements.txt", "python manage.py migrate --noinput", "(cd frontend; pnpm install --frozen-lockfile; pnpm build)", "then restart the server")
}
Write-Host "StillOpen update. This will run, in $(Get-Location):"
$steps | ForEach-Object { Write-Host "  - $_" }
Write-Host "Read CHANGELOG.md first, and take a backup (docs/SELF-HOSTING.md)."
if ($DryRun) { Write-Host "Dry run: nothing was changed."; exit 0 }
if (-not $Yes) {
    $answer = Read-Host "Go ahead? [y/N]"
    if ($answer -notin @("y", "Y", "yes")) { Write-Host "Cancelled."; exit 1 }
}

git pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($useDocker) {
    docker compose -f $composeFile up -d --build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    python manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Push-Location frontend
    try { pnpm install --frozen-lockfile; pnpm build } finally { Pop-Location }
    Write-Host "Done. Restart the server now."
}
Write-Host "Updated to $(git rev-parse --short HEAD)."
