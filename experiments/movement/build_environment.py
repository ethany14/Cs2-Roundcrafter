import json,sqlite3,time,sys
from pathlib import Path
import numpy as np
from cs2_agent.environment_evidence import load_map,build,NAMES
ROOT=Path.cwd();OUT=ROOT/'outputs/movement/environment';rawdir=ROOT/'data/movement/environment';ds=json.loads((ROOT/'data/movement/dataset.json').read_text());profiles=json.loads((ROOT/'data/sounds/profiles.json').read_text());records={};meshes={};start=time.time();db=sqlite3.connect(ROOT/'data/maps/smoke-frames.sqlite')
for d in sorted(ds,key=lambda x:x['map']):
 path=OUT/(d['sha256']+'.json')
 if path.exists() and '--force' not in sys.argv:records[d['sha256']]=json.loads(path.read_text());continue
 if d['map'] not in meshes:meshes={d['map']:load_map(d['map'])}
 raw=json.loads((rawdir/(d['sha256']+'.json')).read_text());rows=[]
 for sample in raw['chosen']:
  vector,details=build(raw,sample,meshes[d['map']],profiles,d['sha256'],d['map'],db);rows.append({'index':sample['index'],'features':vector,'details':details})
 path.write_text(json.dumps(rows));records[d['sha256']]=rows;print(d['map'],d['member'],len(rows),round(time.time()-start,1),flush=True)
index=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text());lookup={k:{r['index']:r for r in v} for k,v in records.items()};vectors=np.array([lookup[r['demo']][r['index']]['features'] for r in index],np.float32);assert np.isfinite(vectors).all();np.save(OUT/'features.npy',vectors);(OUT/'feature-schema.json').write_text(json.dumps({'names':NAMES,'seconds':time.time()-start,'nonzero_counts':dict(zip(NAMES,(vectors!=0).sum(0).tolist()))},indent=2));print('DONE',vectors.shape,flush=True)
