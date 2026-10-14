import hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SRC=Path(r'C:\Users\zhiyu\Downloads\csdemo')
OUT=ROOT/'data/movement'
OUT.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
seen={}; demos={}; records=[]
for p in sorted(SRC.glob('*.rar')):
 h=sha(p)
 if h in seen:
  records.append({'archive':p.name,'sha256':h,'duplicate_of':seen[h]});continue
 seen[h]=p.name
 group=h[:16]; dest=OUT/'demos'/group;dest.mkdir(parents=True,exist_ok=True)
 members=subprocess.check_output([r'C:\Windows\System32\tar.exe','-tf',str(p)],text=True).splitlines()
 members=[m for m in members if m.lower().endswith('.dem')]
 if any(Path(m).is_absolute() or '..' in Path(m).parts or ':' in m for m in members):raise ValueError('Unsafe archive member')
 rows=[]
 for m in members:
  target=dest/m
  if not target.exists():subprocess.run([r'C:\Windows\System32\tar.exe','-xf',str(p),'-C',str(dest),m],check=True)
  dh=sha(target)
  row={'path':str(target),'sha256':dh,'group':group,'member':m}
  if dh in demos:row['duplicate_of']=demos[dh]
  else:demos[dh]=str(target)
  rows.append(row)
 records.append({'archive':p.name,'sha256':h,'group':group,'demos':rows})
 (OUT/'inventory.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
 print(json.dumps({'archive':p.name,'maps':len(rows),'unique_archives':len(seen)},ensure_ascii=False),flush=True)
(OUT/'inventory.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print('DONE',len(seen),'archives',len(demos),'unique demos',flush=True)
