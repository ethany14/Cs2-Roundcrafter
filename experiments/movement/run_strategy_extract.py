import json,subprocess,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/strategy';OUT.mkdir(exist_ok=True);rawdir=ROOT/'data/movement/strategy';rawdir.mkdir(exist_ok=True)
ds=json.loads((ROOT/'data/movement/dataset.json').read_text());start=time.time()
for d in ds:
 dest=rawdir/(d['sha256']+'.json')
 if dest.exists() and '--force' not in sys.argv:continue
 r=subprocess.run(['node',str(ROOT/'experiments/movement/extract_strategy.cjs'),d['path'],str(dest)],capture_output=True,text=True)
 print(d['member'],r.returncode,r.stdout.strip(),r.stderr.strip(),round(time.time()-start,1),flush=True)
 if r.returncode:raise RuntimeError('Extraction failed')
print('DONE',flush=True)
