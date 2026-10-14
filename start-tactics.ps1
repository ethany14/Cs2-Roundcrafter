$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = 'backend'
& ./.venv/Scripts/python.exe -m cs2_agent.tactics_server
