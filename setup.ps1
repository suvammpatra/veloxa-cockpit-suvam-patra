<#
.SYNOPSIS
  First-time setup: virtual environment, requirements and local configuration (.env).
.DESCRIPTION
  Creates .venv if it is missing, installs requirements.txt into it, checks the release pack
  folder (read-only) and records the data folder, port and release pack location in .env,
  which is not committed. It never ingests data and never touches a database.
  Next step: .\setup-demo-data.ps1 (once), then .\start.ps1.
.EXAMPLE
  .\setup.ps1 -SourcePack 'D:\packs\veloxa-release'
.EXAMPLE
  .\setup.ps1 -DataDir 'D:\veloxa-demo-data' -Port 8010
#>
param(
    [string]$SourcePack,
    [string]$DataDir,
    [int]$Port
)
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
Set-Location $script:RepoRoot
Write-Host "Veloxa CXO Cockpit setup in $script:RepoRoot" -ForegroundColor Cyan

# 1. Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { Write-Status FAIL 'python' 'not found on PATH. Install Python 3.11 or later and open a new PowerShell.'; exit 1 }
$version = (& $python.Source -c "import sys; print('%d.%d' % sys.version_info[:2])").Trim()
if ([version]$version -lt [version]'3.11') { Write-Status FAIL 'python' "$version at $($python.Source); 3.11 or later is needed"; exit 1 }
Write-Status PASS 'python' "$version at $($python.Source)"

# 2. Virtual environment (created only when missing) and requirements
if (Test-Path -LiteralPath $script:VenvPython) {
    Write-Status PASS '.venv' 'already present; not recreated'
} else {
    & $python.Source -m venv (Join-Path $script:RepoRoot '.venv')
    if ($LASTEXITCODE -ne 0) { Write-Status FAIL '.venv' 'could not be created'; exit 1 }
    Write-Status PASS '.venv' 'created'
}
& $script:VenvPython -m pip install --disable-pip-version-check -q -r (Join-Path $script:RepoRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Write-Status FAIL 'requirements' 'pip install failed; see the messages above'; exit 1 }
Write-Status PASS 'requirements' 'installed into .venv'

# 3. Configuration: parameters, then the existing .env, then defaults
$config = Get-VeloxaConfig -DataDir $DataDir -Port $Port -SourcePack $SourcePack
try { Assert-ExternalDataDir $config.DataDir } catch { Write-Status FAIL 'data folder' $_.Exception.Message; exit 1 }
if (-not (Test-Path -LiteralPath $config.DataDir)) {
    New-Item -ItemType Directory -Path $config.DataDir | Out-Null      # an empty folder only; no database
    Write-Status PASS 'data folder' "created $($config.DataDir) (empty)"
} else {
    Write-Status PASS 'data folder' $config.DataDir
}
$values = @{ VELOXA_DATA_DIR = $config.DataDir; VELOXA_PORT = $config.Port }
if ($config.SourcePack) { $values['VELOXA_SOURCE_PACK'] = $config.SourcePack }
Set-DotEnvValues $values
Write-Status PASS '.env' "VELOXA_DATA_DIR, VELOXA_PORT$(if ($config.SourcePack) { ', VELOXA_SOURCE_PACK' }) recorded (this file is not committed)"

# 4. Release pack (read-only check)
$packOk = Test-SourcePack $config.SourcePack

# 5. Current state of the demo database (read-only)
Invoke-WithVeloxaEnv $config { & $script:VenvPython -m app.readiness | Out-Null }
$ready = ($LASTEXITCODE -eq 0)
Write-Host ''
if ($ready) {
    Write-Host 'Setup complete. The demo database is ready: run .\start.ps1' -ForegroundColor Green
} elseif ($packOk) {
    Write-Host 'Setup complete. Next, load the release pack once: .\setup-demo-data.ps1   then: .\start.ps1' -ForegroundColor Yellow
} else {
    Write-Host 'Setup complete, but the release pack is not ready. Re-run with -SourcePack <folder that holds the four day folders>, then .\setup-demo-data.ps1' -ForegroundColor Yellow
}
exit 0
