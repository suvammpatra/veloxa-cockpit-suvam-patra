# Shared helpers for setup.ps1, setup-demo-data.ps1, start.ps1 and verify.ps1 (ARCHITECTURE.md 16.20).
# Dot-source only. Nothing here starts, stops or deletes anything.

$ErrorActionPreference = 'Stop'
$script:RepoRoot = Split-Path -Parent $PSScriptRoot   # this file lives in <repository>\scripts
$script:EnvFile = Join-Path $script:RepoRoot '.env'
$script:VenvPython = Join-Path $script:RepoRoot '.venv\Scripts\python.exe'
$script:DefaultPort = 8010

# The release pack: day folder, release day, and the --exported-on date used by the validated procedure.
$script:PackDays = @(
    @{ Folder = 'Day1_Mon_16Nov'; Release = '2026-11-16'; ExportedOn = $null;        Files = 15 },
    @{ Folder = 'Day2_Tue_17Nov'; Release = '2026-11-17'; ExportedOn = '2026-10-31'; Files = 10 },
    @{ Folder = 'Day3_Wed_18Nov'; Release = '2026-11-18'; ExportedOn = '2026-10-31'; Files = 14 },
    @{ Folder = 'Day4_Thu_19Nov'; Release = '2026-11-19'; ExportedOn = $null;        Files = 2 }
)

function Write-Status([string]$Status, [string]$Name, [string]$Detail = '') {
    $colour = @{ PASS = 'Green'; WARN = 'Yellow'; FAIL = 'Red'; INFO = 'Cyan' }[$Status]
    if (-not $colour) { $colour = 'Gray' }
    Write-Host ('{0,-4}  {1}' -f $Status, $Name) -ForegroundColor $colour -NoNewline
    if ($Detail) { Write-Host ": $Detail" } else { Write-Host '' }
}

function Read-DotEnv {
    # KEY=VALUE lines; surrounding quotes are removed when they match. Comments and blanks are skipped.
    $values = @{}
    if (Test-Path -LiteralPath $script:EnvFile) {
        foreach ($line in [IO.File]::ReadAllLines($script:EnvFile)) {
            if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
            $key, $value = $line.Split('=', 2)
            $value = $value.Trim()
            if ($value.Length -ge 2 -and (($value[0] -eq '"' -and $value[-1] -eq '"') -or
                                          ($value[0] -eq "'" -and $value[-1] -eq "'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$key.Trim()] = $value
        }
    }
    return $values
}

function Set-DotEnvValues([hashtable]$Values) {
    # Updates or appends the given keys. Every other line of .env is kept as it was.
    $lines = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $script:EnvFile) {
        $lines.AddRange([string[]][IO.File]::ReadAllLines($script:EnvFile))
    } elseif (Test-Path -LiteralPath (Join-Path $script:RepoRoot '.env.example')) {
        $lines.AddRange([string[]][IO.File]::ReadAllLines((Join-Path $script:RepoRoot '.env.example')))
    }
    foreach ($key in $Values.Keys) {
        $entry = "$key=$($Values[$key])"
        $index = -1
        for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match "^\s*$([regex]::Escape($key))\s*=") { $index = $i } }
        if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
    }
    [IO.File]::WriteAllLines($script:EnvFile, $lines.ToArray(), (New-Object System.Text.UTF8Encoding($false)))
}

function Get-VeloxaConfig([string]$DataDir, [int]$Port, [string]$SourcePack) {
    # Parameters win; then .env; then defaults. The default data folder sits next to the repository.
    $envValues = Read-DotEnv
    if (-not $DataDir) { $DataDir = $envValues['VELOXA_DATA_DIR'] }
    if (-not $DataDir) { $DataDir = Join-Path (Split-Path -Parent $script:RepoRoot) 'veloxa-demo-data' }
    if (-not [IO.Path]::IsPathRooted($DataDir)) { $DataDir = Join-Path $script:RepoRoot $DataDir }   # as the app resolves it
    if (-not $Port) { $Port = [int]($envValues['VELOXA_PORT']) }
    if (-not $Port) { $Port = $script:DefaultPort }
    if (-not $SourcePack) { $SourcePack = $envValues['VELOXA_SOURCE_PACK'] }
    return [pscustomobject]@{
        DataDir    = [IO.Path]::GetFullPath($DataDir)
        Port       = $Port
        SourcePack = $SourcePack
        Database   = Join-Path ([IO.Path]::GetFullPath($DataDir)) 'cockpit.db'
    }
}

function Test-InsideRepository([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    $root = [IO.Path]::GetFullPath($script:RepoRoot).TrimEnd('\') + '\'
    return $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-ExternalDataDir([string]$DataDir) {
    if (Test-InsideRepository $DataDir) {
        throw "The data folder '$DataDir' is inside the repository. Demo data must live outside it (data\cockpit.db is never used). Run .\setup.ps1 -DataDir <folder outside the repository>."
    }
}

function Assert-VenvPython {
    if (-not (Test-Path -LiteralPath $script:VenvPython)) {
        throw "The project virtual environment is missing ($script:VenvPython). Run .\setup.ps1 first."
    }
    return $script:VenvPython
}

function Get-PortOwner([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)" -ErrorAction SilentlyContinue
    $parent = $null
    if ($proc) { $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)" -ErrorAction SilentlyContinue }
    return [pscustomobject]@{
        ProcessId        = $conn.OwningProcess
        Name             = $(if ($proc) { $proc.Name } else { 'unknown' })
        Executable       = $(if ($proc) { $proc.ExecutablePath } else { $null })
        CommandLine      = $(if ($proc) { $proc.CommandLine } else { $null })
        ParentExecutable = $(if ($parent) { $parent.ExecutablePath } else { $null })
    }
}

function Test-RunsFromVenv([pscustomobject]$Owner) {
    # On Windows, .venv\Scripts\python.exe is a launcher that starts the base interpreter with the
    # virtual environment's packages: the listening process names the launcher in its command line,
    # and the launcher is its parent.
    $venv = [IO.Path]::GetFullPath($script:VenvPython)
    if ($Owner.CommandLine -and $Owner.CommandLine.IndexOf($venv, [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    foreach ($exe in @($Owner.Executable, $Owner.ParentExecutable)) {
        if ($exe -and [IO.Path]::GetFullPath($exe) -eq $venv) { return $true }
    }
    return $false
}

function Invoke-WithVeloxaEnv([pscustomobject]$Config, [scriptblock]$Body) {
    # Sets VELOXA_DATA_DIR and VELOXA_PORT for the commands in $Body only, then restores the session.
    $saved = @{ VELOXA_DATA_DIR = $env:VELOXA_DATA_DIR; VELOXA_PORT = $env:VELOXA_PORT }
    try {
        $env:VELOXA_DATA_DIR = $Config.DataDir
        $env:VELOXA_PORT = [string]$Config.Port
        & $Body
    } finally {
        foreach ($k in $saved.Keys) {
            if ($null -eq $saved[$k]) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue } else { Set-Item "Env:$k" $saved[$k] }
        }
    }
}

function Test-SourcePack([string]$SourcePack) {
    # Read-only. Returns $true when the four day folders are present with their expected file counts.
    $ok = $true
    if (-not $SourcePack) { Write-Status FAIL 'source pack' 'not configured. Run .\setup.ps1 -SourcePack <folder that holds Day1_Mon_16Nov ... Day4_Thu_19Nov>'; return $false }
    if (-not (Test-Path -LiteralPath $SourcePack -PathType Container)) { Write-Status FAIL 'source pack' "folder not found: $SourcePack"; return $false }
    foreach ($day in $script:PackDays) {
        $folder = Join-Path $SourcePack $day.Folder
        if (-not (Test-Path -LiteralPath $folder -PathType Container)) { Write-Status FAIL "source pack $($day.Folder)" 'folder missing'; $ok = $false; continue }
        $n = @(Get-ChildItem -LiteralPath $folder -Recurse -File).Count
        if ($n -eq $day.Files) { Write-Status PASS "source pack $($day.Folder)" "$n files" }
        else { Write-Status WARN "source pack $($day.Folder)" "$n files (the validated pack has $($day.Files))" }
    }
    return $ok
}
