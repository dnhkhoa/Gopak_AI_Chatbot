$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Write-Step($Message) {
    Write-Host "[setup] $Message"
}

function Get-PythonVersion($Command, [string[]]$Args) {
    try {
        $output = & $Command @Args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($output | Select-Object -First 1).Trim()
    } catch {
        return $null
    }
}

function Select-Python {
    $candidates = @(
        @{ Label = "py -3.11"; Command = "py"; Args = @("-3.11") },
        @{ Label = "py -3.10"; Command = "py"; Args = @("-3.10") },
        @{ Label = "python"; Command = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) {
            continue
        }
        $version = Get-PythonVersion $candidate.Command $candidate.Args
        if ([string]::IsNullOrWhiteSpace($version)) {
            continue
        }
        $parts = $version.Split(".")
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        if ($major -eq 3 -and ($minor -eq 11 -or $minor -eq 10)) {
            return [pscustomobject]@{
                Label = $candidate.Label
                Command = $candidate.Command
                Args = $candidate.Args
                Version = $version
            }
        }
    }

    throw "No compatible Python found. Install Python 3.11 or Python 3.10, then rerun .\setup.ps1."
}

function Get-VenvPythonVersion {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        return $null
    }
    try {
        $output = & ".\.venv\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($output | Select-Object -First 1).Trim()
    } catch {
        return $null
    }
}

Write-Step "Detecting Python"
$python = Select-Python
Write-Step "Using $($python.Label) ($($python.Version))"

$venvVersion = Get-VenvPythonVersion
if ($null -eq $venvVersion) {
    if (Test-Path ".venv") {
        $backup = ".venv.broken-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Write-Step "Existing .venv is invalid; moving it to $backup"
        Move-Item -LiteralPath ".venv" -Destination $backup
    }
    Write-Step "Creating .venv"
    & $python.Command @($python.Args + @("-m", "venv", ".venv"))
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv using $($python.Label)."
    }
    $venvVersion = Get-VenvPythonVersion
}

if ($null -eq $venvVersion) {
    throw ".venv was not created correctly; .venv\Scripts\python.exe is missing or unusable."
}

$venvParts = $venvVersion.Split(".")
if ([int]$venvParts[0] -ne 3 -or (([int]$venvParts[1] -ne 11) -and ([int]$venvParts[1] -ne 10))) {
    throw ".venv uses unsupported Python $venvVersion. Remove or rename .venv and rerun setup with Python 3.11 or 3.10."
}

Write-Step "Validated .venv Python $venvVersion"
Write-Step "Upgrading pip"
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip

Write-Step "Installing backend dependencies"
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Step "Creating .env from .env.example"
    Copy-Item ".env.example" ".env"
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js was not found on PATH. Install Node.js and rerun .\setup.ps1."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found on PATH. Install npm and rerun .\setup.ps1."
}

Write-Step "Installing frontend dependencies"
Push-Location "frontend"
try {
    npm install
} finally {
    Pop-Location
}

Write-Step "Running dependency smoke checks"
& ".\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, pandas, duckdb, pyarrow; print('backend dependency smoke ok')"
Push-Location "frontend"
try {
    npm --version | Out-Host
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run .\run.ps1 to start the FastAPI backend and React frontend."
