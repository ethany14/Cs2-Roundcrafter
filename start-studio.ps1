$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& ./.venv/Scripts/python.exe -m cs2_agent.studio_server
