import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/movement/joint';OUT.mkdir(exist_ok=True)
rows=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text());ds=json.loads((ROOT/'data/movement/dataset.json').read_text())
for d in ds:
 indices=[r['index'] for r in rows if r['demo']==d['sha256']];dest=OUT/(d['sha256']+'.json');sel=OUT/'selection.json';sel.write_text(json.dumps(indices))
 if dest.exists():continue
 r=subprocess.run(['node',str(ROOT/'experiments/movement/extract_joint.cjs'),d['path'],str(sel),str(dest)],capture_output=True,text=True)
 print(d['member'],r.returncode,r.stdout,r.stderr,flush=True)
 if r.returncode:raise RuntimeError('joint extraction failed')
print('DONE',len(ds),flush=True)
