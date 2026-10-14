import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];out=ROOT/'data/movement';(out/'samples').mkdir(exist_ok=True)
records=json.loads((out/'inventory.json').read_text());results=[]
for archive in records:
 for d in archive.get('demos',[]):
  if 'duplicate_of' in d:continue
  target=out/'samples'/(d['sha256']+'.json')
  if not target.exists():
   result=subprocess.run(['node',str(ROOT/'experiments/movement/extract.cjs'),d['path'],str(target)],capture_output=True,text=True)
   print(archive['archive'],d['member'],result.returncode,result.stdout,result.stderr,flush=True)
   if result.returncode:results.append({**d,'error':result.stderr});continue
  info=json.loads(target.read_text());results.append({**d,'archive':archive['archive'],'sample_file':str(target),'map':info['map'],'rounds':info['rounds'],'samples':len(info['samples'])})
  (out/'dataset.json').write_text(json.dumps(results,indent=2))
print('DONE',len(results),flush=True)
