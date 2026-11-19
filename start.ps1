<#
.SYNOPSIS
  Start the cockpit with the project's .venv Python and the external demo database.
.DESCRIPTION
  Refuses to start when the virtual environment is missing, when the database is missing or
  empty, or when the port is taken, and says what to do instead. It never creates an empty
  database and never stops another process. Press Ctrl+C to stop the server.
.EXAMPLE
  .\start.ps1
.EXAMPLE
  .\start.ps1 -Port 8011
#>
param(
    [int]$Port,
    [string]$DataDir
)
. (Join-Path $PSScriptRoot 'scripts\common.ps1')
Set-Location $script:RepoRoot
try { $py = Assert-VenvPython } catch { Write-Status FAIL '.venv' $_.Exception.Message; exit 1 }
$config = Get-VeloxaConfig -DataDir $DataDir -Port $Port
try { Assert-ExternalDataDir $config.DataDir } catch { Write-Status FAIL 'data folder' $_.Exception.Message; exit 1 }
Write-Status INFO 'python' $py
Write-Status INFO 'database' $config.Database

# The demo data must be there before the server starts (read-only check; creates nothing).
Invoke-WithVeloxaEnv $config { & $py -m app.readiness }
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'Not starting: the demo database is not ready (see FAIL above).' -ForegroundColor Red
    Write-Host 'First time? Run .\setup.ps1, then .\setup-demo-data.ps1, then .\start.ps1 again.' -ForegroundColor Red
    exit 1
}

# The port must be free; another process is never stopped.
$owner = Get-PortOwner $config.Port
if ($owner) {
    Write-Host ''
    Write-Status FAIL "port $($config.Port)" "already in use by $($owner.Name) (PID $($owner.ProcessId))"
    if ($owner.CommandLine -match '-m app(\s|$)') {
        Write-Host "It looks like the cockpit is already running: open http://127.0.0.1:$($config.Port)/ or stop it with Ctrl+C in its window." -ForegroundColor Yellow
    } else {
        Write-Host "Choose another port: .\start.ps1 -Port <number>, or set VELOXA_PORT in .env." -ForegroundColor Yellow
    }
    exit 1
}

Write-Host ''
Write-Host "Starting the cockpit at http://127.0.0.1:$($config.Port)/   (Ctrl+C to stop)" -ForegroundColor Green
Invoke-WithVeloxaEnv $config { & $py -m app }
exit $LASTEXITCODE
