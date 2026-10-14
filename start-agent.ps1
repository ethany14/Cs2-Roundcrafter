param([switch]$Smoke, [string]$Task, [string]$Resume)
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install this project first; see README.md.' }
Push-Location $PSScriptRoot
try {
    if ($Smoke) { & $pythonPath -m cs2_agent --smoke }
    elseif ($Resume) { & $pythonPath -m cs2_agent --resume $Resume }
    elseif ($Task) { & $pythonPath -m cs2_agent --task $Task }
    else { & $pythonPath -m cs2_agent --help }
    exit $LASTEXITCODE
} finally { Pop-Location }
