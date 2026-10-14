# Decompile CS2 equipment icons (weapons, grenades, armor, C4) from the local install for the local UI only.
param([string]$GameDirectory = 'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo')
$projectDirectory = Split-Path -Parent $PSScriptRoot
$viewerPath = Join-Path $projectDirectory 'work\vrf\bin\Source2Viewer-CLI.exe'
$package = Join-Path $GameDirectory 'pak01_dir.vpk'
if (-not (Test-Path -LiteralPath $viewerPath)) { throw 'Prepare the official Source2Viewer CLI in work/vrf/bin first.' }
if (-not (Test-Path -LiteralPath $package)) { throw 'Local CS2 pak01_dir.vpk not found.' }
& $viewerPath -i $package -f 'panorama/images/icons/equipment/' -o (Join-Path $projectDirectory 'data\icons') -d
exit $LASTEXITCODE
