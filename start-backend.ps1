$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Get-EnvValue($Name, $Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value
}

function Test-PortInUse($Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

$hostName = Get-EnvValue "API_HOST" "127.0.0.1"
$port = [int](Get-EnvValue "API_PORT" "8000")

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH."
}

python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "FastAPI/Uvicorn are not installed. Run: python -m pip install -r requirements.txt"
}

if (Test-PortInUse $port) {
    throw "Port $port is already in use. Stop the existing process or set API_PORT to another value."
}

python -m uvicorn backend.main:app --host $hostName --port $port
