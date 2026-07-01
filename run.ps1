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
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $response
            }
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

function Stop-ExistingDevProcess($Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    $pids = @($connections | ForEach-Object { $_.OwningProcess } | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique)
    foreach ($pidToStop in $pids) {
        if ($pidToStop -and $pidToStop -ne $PID) {
            $process = Get-Process -Id $pidToStop -ErrorAction SilentlyContinue
            if ($process) {
                Write-Host "[run] Stopping existing process on port ${Port}: $($process.ProcessName) PID $pidToStop"
                Stop-Process -Id $pidToStop -Force
            }
        }
    }
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run .\setup.ps1 first."
}

if (-not (Test-Path "frontend\node_modules")) {
    throw "Frontend dependencies not found. Run .\setup.ps1 first."
}

$backendHost = Get-EnvValue "API_HOST" "127.0.0.1"
$backendPort = [int](Get-EnvValue "API_PORT" "8000")
$frontendHost = "localhost"
$frontendPort = [int](Get-EnvValue "FRONTEND_PORT" "3000")
$backendUrl = "http://${backendHost}:${backendPort}"
$healthUrl = "$backendUrl/api/health"
$frontendUrl = "http://${frontendHost}:${frontendPort}"

New-Item -ItemType Directory -Force -Path "logs" | Out-Null

Write-Host "[run] Validating backend dependencies"
& ".\.venv\Scripts\python.exe" -c "import fastapi, uvicorn, pandas, duckdb; print('backend dependency smoke ok')"

Write-Host "[run] Validating production data sources"
& ".\.venv\Scripts\python.exe" scripts_ingest.py

Write-Host "[run] Checking Ollama"
$ollamaStatus = "unavailable"
try {
    $settingsJson = & ".\.venv\Scripts\python.exe" -c "from src.config import get_settings; s=get_settings(); print(s.ollama_base_url + '|' + s.ollama_model)"
    $settingsParts = $settingsJson.Split("|")
    $ollamaBase = $settingsParts[0]
    $ollamaModel = $settingsParts[1]
    $tags = Invoke-WebRequest -Uri "$ollamaBase/api/tags" -UseBasicParsing -TimeoutSec 3
    if ($tags.Content -like "*$ollamaModel*") {
        $ollamaStatus = "ready: $ollamaModel"
    } else {
        $ollamaStatus = "reachable but model not listed: $ollamaModel"
    }
} catch {
    $ollamaStatus = "unavailable: $($_.Exception.Message)"
}
Write-Host "[run] Ollama status: $ollamaStatus"

Stop-ExistingDevProcess $backendPort
Stop-ExistingDevProcess $frontendPort

$backendOut = Join-Path $PSScriptRoot "logs\backend-dev.log"
$backendErr = Join-Path $PSScriptRoot "logs\backend-dev.err.log"
$frontendOut = Join-Path $PSScriptRoot "logs\frontend-dev.log"
$frontendErr = Join-Path $PSScriptRoot "logs\frontend-dev.err.log"

Write-Host "[run] Starting backend on $backendUrl"
$backendProcess = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", $backendHost, "--port", "$backendPort") `
    -WorkingDirectory $PSScriptRoot `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -WindowStyle Hidden `
    -PassThru

Write-Host "[run] Waiting for backend health"
$health = Wait-Http $healthUrl 60

Write-Host "[run] Starting frontend on $frontendUrl"
$frontendProcess = Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev", "--", "--host", $frontendHost, "--port", "$frontendPort") `
    -WorkingDirectory (Join-Path $PSScriptRoot "frontend") `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -WindowStyle Hidden `
    -PassThru

Write-Host "[run] Waiting for frontend"
$frontend = Wait-Http $frontendUrl 60

Write-Host ""
Write-Host "Frontend URL: $frontendUrl"
Write-Host "Backend URL:  $backendUrl"
Write-Host "Health URL:   $healthUrl"
Write-Host "Health status: HTTP $($health.StatusCode)"
Write-Host "Frontend status: HTTP $($frontend.StatusCode)"
Write-Host "Ollama status: $ollamaStatus"
Write-Host "Backend PID:  $($backendProcess.Id)"
Write-Host "Frontend PID: $($frontendProcess.Id)"
Write-Host "Backend log:  $backendOut"
Write-Host "Frontend log: $frontendOut"
Write-Host "Stop command: Stop-Process -Id $($backendProcess.Id),$($frontendProcess.Id)"
Write-Host ""
Write-Host "Application is running for manual testing."
