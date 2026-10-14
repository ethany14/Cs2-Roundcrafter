param([string]$GameDirectory = 'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo')
$projectDirectory = Split-Path -Parent $PSScriptRoot
$viewerPath = Join-Path $projectDirectory 'work\vrf\bin\Source2Viewer-CLI.exe'
$mapPackage = Join-Path $GameDirectory 'maps\de_dust2.vpk'
if (-not (Test-Path -LiteralPath $viewerPath)) { throw 'Prepare the checksum-verified official Source2Viewer CLI 20.0 in work/vrf/bin first.' }
if (-not (Test-Path -LiteralPath $mapPackage)) { throw 'Local Dust2 map package not found.' }
Push-Location $projectDirectory
try {
    & $viewerPath -i $mapPackage -f maps/de_dust2/world_physics.vmdl_c -o data/maps/world_physics.vmdl_c
    if ($LASTEXITCODE -ne 0) { throw 'Physics resource extraction failed.' }
    & $viewerPath -i $mapPackage -f maps/de_dust2/world_physics.vmdl_c -o data/maps/current-physics --gltf_export_format gltf -d
    if ($LASTEXITCODE -ne 0) { throw 'Physics export failed.' }
    & $viewerPath -i $mapPackage -e vents_c -o data/maps/current-entities -d
    if ($LASTEXITCODE -ne 0) { throw 'Entity export failed.' }
    & $viewerPath -i $mapPackage -f maps/de_dust2/worldnodes/n0_lr0_agg_merge_dust_door -o data/maps/current-doors --gltf_export_format gltf -d
    if ($LASTEXITCODE -ne 0) { throw 'Door export failed.' }
    & $viewerPath -i $mapPackage -f maps/de_dust2/worldnodes/n0_lr0_agg_merge_dust_kasbah_ladder_0.vmdl_c -o data/maps/ladder-merged --gltf_export_format gltf -d
    if ($LASTEXITCODE -ne 0) { throw 'Ladder export failed.' }
    & ./.venv/Scripts/python.exe -m cs2_agent.map_assets
    exit $LASTEXITCODE
} finally { Pop-Location }
