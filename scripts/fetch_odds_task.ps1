# scripts/fetch_odds_task.ps1 -- hourly cron-fed odds cache wrapper (TODOS.md #1).
#
# Invoked by the Windows Scheduled Task "swiss-mc-odds-cologne-stage2" once per hour
# (window extended through 2026-06-16 for Stage 3, June 11-15).
#
# STAGE 3 (2026-06-09): now that the stage-aware fetch lives in the MAIN tree (PR #11), this
# runs the full Stage-3 refresh pipeline there: scripts.refresh_stage3_odds = stage-3 R1 fetch
# (bo3-stamped) -> live Kalshi playoff-qualify mids written as the "qualify" block (logit-
# renormalized to sum 8) -> scripts.fit_qualify rounds-2-5 calibration. Each step is fail-soft:
# a failed fetch leaves the previous cache; a failed qualify pull/fit leaves a valid R1-only
# stage-3 cache (the app falls back to the R1 back-solve, never a crash, never cross-stage).
# The old stage-2 worktree path (.claude/worktrees/stage2-live-odds) is retired.
#
# Secret safety (T-05-SECRET): all pipeline output is discarded; the log line is derived from
# the written cache's _meta, so the OddsPapi apiKey can never reach the log.
# NOTE: ASCII-only on purpose -- PS 5.1 reads UTF-8-no-BOM as cp1252, so a non-ASCII char in a
# string literal (e.g. an em-dash) becomes a curly quote that breaks parsing.
$ErrorActionPreference = 'Continue'
$proj = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mainCache = Join-Path $proj 'data\odds_cache.json'
$logf = Join-Path $proj 'data\odds_fetch.log'
$ts = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'

# Resolve uv: PATH first, then the standard per-user install location.
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE '.local\bin\uv.exe' }

# Guard: the pipeline module must exist in the working tree (e.g. master checked out without
# PR #11 merged). If missing, LEAVE the existing cache intact -- never run the old stage-1 fetch.
if (-not (Test-Path (Join-Path $proj 'scripts\refresh_stage3_odds.py'))) {
    Add-Content -Path $logf -Value "[$ts] SKIP :: refresh_stage3_odds.py missing (branch without PR #11?) -- cache left intact" -Encoding utf8
    return
}

Set-Location $proj
& $uv run python -m scripts.refresh_stage3_odds *> $null
$code = $LASTEXITCODE

$summary = 'no cache file present'
if (Test-Path $mainCache) {
    try {
        $c = Get-Content $mainCache -Raw | ConvertFrom-Json
        $n = ($c.blended.PSObject.Properties | Measure-Object).Count
        $provs = @($c._meta.providers_present) -join ','
        $fit = 'none'
        if ($c._meta.PSObject.Properties.Name -contains 'qualify_fit') { $fit = $c._meta.qualify_fit.converged }
        $summary = "stage=$($c._meta.stage) matches=$n providers=[$provs] qualify_fit=$fit fetched_at=$($c._meta.fetched_at)"
    } catch {
        $summary = "cache parse error: $($_.Exception.Message)"
    }
}
Add-Content -Path $logf -Value "[$ts] exit=$code :: $summary" -Encoding utf8
