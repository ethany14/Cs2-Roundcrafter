param([string]$Match = '2398755', [switch]$Offline, [switch]$Build)
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location $PSScriptRoot
try {
    if ($Build) {
        & $pythonPath -m cs2_agent.casebook build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $pythonPath -m cs2_agent.perception
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    if ($Offline) { & $pythonPath -m cs2_agent.review --match $Match --offline }
    else { & $pythonPath -m cs2_agent.review --match $Match --max-calls 6 }
    exit $LASTEXITCODE
} finally { Pop-Location }
