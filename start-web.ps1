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

function Wait-Http($Url, $Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Milliseconds 700
        }
    }
    return $false
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found on PATH."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js was not found on PATH."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found on PATH."
}

$apiHost = Get-EnvValue "API_HOST" "127.0.0.1"
$apiPort = [int](Get-EnvValue "API_PORT" "8000")
$frontendPort = 5173

if (Test-PortInUse $apiPort) {
    throw "Backend port $apiPort is already in use."
}
if (Test-PortInUse $frontendPort) {
    throw "Frontend port $frontendPort is already in use."
}

if (-not (Test-Path (Join-Path $PSScriptRoot "frontend\node_modules"))) {
    Push-Location (Join-Path $PSScriptRoot "frontend")
    npm install
    Pop-Location
}

$backendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "start-frontend.ps1"

Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$backendScript`""
Start-Sleep -Seconds 2
Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$frontendScript`""

$apiReady = Wait-Http "http://$apiHost`:$apiPort/api/health" 30
$frontendReady = Wait-Http "http://localhost:$frontendPort" 30

if (-not $apiReady) {
    throw "Backend did not become ready at http://$apiHost`:$apiPort."
}
if (-not $frontendReady) {
    throw "Frontend did not become ready at http://localhost:$frontendPort."
}

Start-Process "http://localhost:$frontendPort"
Write-Host "Gopak web is running:"
Write-Host "  Backend:  http://$apiHost`:$apiPort"
Write-Host "  Frontend: http://localhost:$frontendPort"
