import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'data/movement/environment';rows=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text());ds=json.loads((ROOT/'data/movement/dataset.json').read_text())
for d in ds:
 dest=out/(d['sha256']+'.json');selection=out/'selection.json';selection.write_text(json.dumps([r['index'] for r in rows if r['demo']==d['sha256']]))
 if dest.exists():continue
 r=subprocess.run(['node',str(ROOT/'experiments/movement/extract_environment.cjs'),d['path'],str(selection),str(dest)],capture_output=True,text=True);print(d['member'],r.returncode,r.stdout,r.stderr,flush=True)
 if r.returncode:raise RuntimeError('Extraction failure')
print('DONE',flush=True)
