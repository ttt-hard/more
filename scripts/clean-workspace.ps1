<#
.SYNOPSIS
  Clean up all pytest / smoke-test leftover directories from the repo.

.DESCRIPTION
  Python tests and manual smoke scripts drop ~20 tmp folders at both repo
  root and `backend/` level. None of them are needed after the run finishes
  — they are workspace fixtures, transient note stores, and pytest tmp
  dirs. This script wipes them all while preserving:

    - `backend/tests/`            (real pytest suite, 169 tests)
    - `backend/evals/`            (benchmark harness)
    - `backend/app/`              (source)
    - `workspace/`                (personal notes)

  Run from anywhere; paths are anchored to the script location.

.EXAMPLE
  pwsh scripts/clean-workspace.ps1            # dry-run: prints what would be deleted
  pwsh scripts/clean-workspace.ps1 -Apply     # actually delete
#>

param(
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

$Patterns = @(
    # Root-level scratch / smoke leftovers
    "$RepoRoot\scratch-*",
    "$RepoRoot\smoke-*",
    "$RepoRoot\tmp*",

    # backend/ pytest + manual-test leftovers
    "$RepoRoot\backend\.pytest-*",
    "$RepoRoot\backend\.pytest_cache",
    "$RepoRoot\backend\.pytest-tmp",
    "$RepoRoot\backend\.pytest-tmp-*",
    "$RepoRoot\backend\pytest-tmp-*",
    "$RepoRoot\backend\.manual-test-runs",
    "$RepoRoot\backend\.manual-test-runs-*",
    "$RepoRoot\backend\.smoke-*",
    "$RepoRoot\backend\more-smoke-*",
    "$RepoRoot\backend\test-workdirs",
    "$RepoRoot\backend\tmp*",

    # Evaluation scratch
    "$RepoRoot\backend\evals\.eval-workspaces",

    # Frontend build artefacts
    "$RepoRoot\frontend\dist",
    "$RepoRoot\frontend\.vite",

    # Backup files
    "$RepoRoot\frontend\src\*.backup.*.txt",

    # Python cache
    "$RepoRoot\backend\**\__pycache__",
    "$RepoRoot\backend\*.egg-info"
)

$Targets = @()
foreach ($pattern in $Patterns) {
    $matches = Get-ChildItem -Path $pattern -Force -ErrorAction SilentlyContinue
    foreach ($match in $matches) { $Targets += $match.FullName }
}

if ($Targets.Count -eq 0) {
    Write-Host "Nothing to clean — the repo is already tidy." -ForegroundColor Green
    exit 0
}

Write-Host "Found $($Targets.Count) items to remove:" -ForegroundColor Cyan
$Targets | Sort-Object | ForEach-Object { Write-Host "  - $_" -ForegroundColor DarkGray }

if (-not $Apply) {
    Write-Host "`nThis was a DRY RUN. Re-run with -Apply to actually delete." -ForegroundColor Yellow
    exit 0
}

$deleted = 0
foreach ($target in $Targets) {
    try {
        Remove-Item -Path $target -Recurse -Force -ErrorAction Stop
        Write-Host "  deleted  $target" -ForegroundColor Green
        $deleted++
    } catch {
        Write-Host "  SKIPPED  $target   ($_)" -ForegroundColor Red
    }
}
Write-Host "`nDeleted $deleted / $($Targets.Count) items." -ForegroundColor Cyan
