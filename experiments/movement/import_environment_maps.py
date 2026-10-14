import subprocess,json
from pathlib import Path
import numpy as np
from cs2_agent.map_assets import gltf_triangles
ROOT=Path.cwd();GAME=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\maps');out=ROOT/'data/maps/all';out.mkdir(exist_ok=True)
for name in ['de_ancient','de_anubis','de_cache','de_dust2','de_inferno','de_mirage','de_nuke']:
 dest=out/name;dest.mkdir(exist_ok=True);path=dest/'world_physics.gltf'
 if not (dest/'scene.npz').exists():
  r=subprocess.run([str(ROOT/'work/vrf/bin/Source2Viewer-CLI.exe'),'-i',str(GAME/(name+'.vpk')),'-f',f'maps/{name}/world_physics.vmdl_c','-o',str(path),'--gltf_export_format','gltf','-d'],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stdout+r.stderr)
  actual=dest/'world_physics_physics.gltf';groups=[];tris=[];ids=[]
  for t,m in gltf_triangles(actual):
   if set(m.get('InteractAs',[]))&{'playerclip','npcclip','csgo_grenadeclip','sky'}:continue
   ids.extend([len(groups)]*len(t));groups.append(m);tris.append(t)
  np.savez_compressed(dest/'scene.npz',triangles=np.concatenate(tris).astype('float32'),groups=np.array(ids));(dest/'scene.json').write_text(json.dumps({'map':name,'groups':groups,'dynamic_state':'not included; static world collision only'}))
 print(name,'ready',flush=True)
