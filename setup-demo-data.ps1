<#
.SYNOPSIS
  One-time load of the release pack (Days 1-4) and the three reviewed files into the external demo database.
.DESCRIPTION
  Checks the release pack and the target first. It ingests only into a database that is missing or
  empty; a database that already holds data is never ingested into again, so nothing is duplicated
  or overwritten. The release pack is only read. Uses .venv\Scripts\python.exe throughout.
  Order: Day 1 to Day 4 with their release days, then the reviewed aliases, conflicts and
  organisation records, then a strict readiness summary.
.EXAMPLE
  .\setup-demo-data.ps1
#>
param(
    [string]$SourcePack,
    [string]$DataDir
)
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
Set-Location $script:RepoRoot
try { $py = Assert-VenvPython } catch { Write-Status FAIL '.venv' $_.Exception.Message; exit 1 }
$config = Get-VeloxaConfig -DataDir $DataDir -SourcePack $SourcePack
try { Assert-ExternalDataDir $config.DataDir } catch { Write-Status FAIL 'data folder' $_.Exception.Message; exit 1 }
Write-Status INFO 'python' $py
Write-Status INFO 'target database' $config.Database

# 1. The release pack, read-only
if (-not (Test-SourcePack $config.SourcePack)) { Write-Host 'Nothing was ingested.' -ForegroundColor Red; exit 1 }

# 2. The target must be missing or empty
$state = Invoke-WithVeloxaEnv $config { & $py -m app.readiness --json --strict } | ConvertFrom-Json
$counts = $state.counts
if ($state.ok) {
    Write-Status PASS 'demo database' 'already loaded with the expected Days 1-4 data; nothing to do'
    exit 0
}
if ($counts.exists -and ($counts.sources -gt 0 -or $counts.evidence -gt 0 -or $counts.persons -gt 0 -or $counts.aliases -gt 0)) {
    Write-Status FAIL 'demo database' ("already holds data ({0} sources, {1} evidence rows, {2} people, {3} aliases) but not the expected Days 1-4 set. " -f $counts.sources, $counts.evidence, $counts.persons, $counts.aliases)
    Write-Host 'Not ingesting again, to avoid duplicates. Check it with .\verify.ps1, or load into a new empty folder: .\setup.ps1 -DataDir <new folder>, then .\setup-demo-data.ps1.' -ForegroundColor Red
    exit 1
}
$payroll = Join-Path $config.DataDir 'payroll.db'
if (Test-Path -LiteralPath $payroll) {
    Write-Status FAIL 'payroll store' "$payroll already exists although the database is empty. Not ingesting; use a new empty folder."
    exit 1
}
Write-Status PASS 'demo database' $(if ($counts.exists) { 'present and empty; loading' } else { 'not created yet; loading' })

# 3. Ingest, in release order; stop at the first failure
$failed = $false
Invoke-WithVeloxaEnv $config {
    foreach ($day in $script:PackDays) {
        $args_ = @('-m', 'app.ingestion', 'ingest', (Join-Path $config.SourcePack $day.Folder), '--release-day', $day.Release)
        if ($day.ExportedOn) { $args_ += @('--exported-on', $day.ExportedOn) }
        Write-Host ''
        Write-Status INFO "ingest $($day.Folder)" "release day $($day.Release)$(if ($day.ExportedOn) { ", exported-on $($day.ExportedOn)" })"
        & $py @args_ | Select-Object -Last 2 | ForEach-Object { Write-Host "      $_" }
        if ($LASTEXITCODE -ne 0) { Write-Status FAIL "ingest $($day.Folder)" "exit code $LASTEXITCODE; stopped"; $script:failed = $true; return }
    }
    foreach ($step in @(@('aliases', 'data\aliases_reviewed.csv'), @('conflicts', 'data\conflicts_reviewed.json'),
                        @('org', 'data\org_reviewed.json'))) {
        Write-Host ''
        Write-Status INFO "load $($step[1])"
        & $py -m app.ingestion $step[0] (Join-Path $script:RepoRoot $step[1]) | Select-Object -Last 4 | ForEach-Object { Write-Host "      $_" }
        if ($LASTEXITCODE -ne 0) { Write-Status FAIL "load $($step[1])" "exit code $LASTEXITCODE; stopped"; $script:failed = $true; return }
    }
}
if ($script:failed) {
    Write-Host 'Loading stopped. Do not re-run into this folder; check it with .\verify.ps1 and use a new empty folder if needed.' -ForegroundColor Red
    exit 1
}

# 4. Summary
Write-Host ''
Write-Host 'Summary (read-only check):' -ForegroundColor Cyan
Invoke-WithVeloxaEnv $config { & $py -m app.readiness --strict }
if ($LASTEXITCODE -ne 0) { Write-Host 'Loaded, but the counts differ from the validated Days 1-4 set; see above.' -ForegroundColor Yellow; exit 1 }
Write-Host 'Demo data loaded. Start the cockpit with .\start.ps1' -ForegroundColor Green
exit 0
