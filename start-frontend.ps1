$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "frontend")

function Test-PortInUse($Port) {
    $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js was not found on PATH."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found on PATH."
}

if (Test-PortInUse 5173) {
    throw "Port 5173 is already in use. Stop the existing process or change the Vite port."
}

if (-not (Test-Path "node_modules")) {
    npm install
}

npm run dev
