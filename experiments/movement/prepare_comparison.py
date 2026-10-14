import json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/movement';OUT=ROOT/'outputs/movement/comparison'
def prompt(h,c):
 return ('CS2 player-known state. Predict local XY movement at +0.5,+1,+2 seconds. '
 'Coordinates: forward/right relative to current aim; 1 unit=250 game units. '
 'Past frames -2,-1.5,-1,-0.5,0 seconds. Each row: forward,right,height,sin_yaw_delta,cos_yaw_delta,pitch/90,crouch,flash_seconds/5.\n'
 +json.dumps(h,separators=(',',':'))+'\nCurrent context: health/100,armor/100,is_CT,round_seconds/120,team_alive/5,enemy_alive/5,bomb_planted,bomb_age/40,then two nearest teammates (forward,right,height,present).\n'
 +json.dumps(c,separators=(',',':')))
def main():
 OUT.mkdir(exist_ok=True);ds=json.loads((DATA/'dataset.json').read_text());assert len(ds)==77 and all('sample_file' in d for d in ds)
 groups=sorted(set(d['group'] for d in ds));all_maps={d['map'] for d in ds};rng=np.random.default_rng(20261013)
 for attempt in range(10000):
  order=rng.permutation(groups).tolist();split={g:('test' if i<6 else 'validation' if i<11 else 'train') for i,g in enumerate(order)}
  if all({d['map'] for d in ds if split[d['group']]==part}==all_maps for part in ['train','validation','test']):break
 else:raise ValueError('Cannot obtain map coverage without splitting series')
 protocol={'schema':1,'split':split,'split_policy':'seed 20261013; first randomized series split with all seven maps represented in each partition; labels never inspected','sampling':'64 uniformly random windows per unique demo without replacement; RNG derived from demo SHA256; independent of labels','seeds':[7,17,29],'epochs':100,'batch_size':256,'selection':'minimum validation ADE; three-seed mean predictions, no test tuning','model_revision':'1cfa9a7208912126459214e8b04321603b3df60c','pooling':'last-layer masked mean','model':'Qwen3-4B','precision':'bfloat16 frozen inference','information':'same rounded causal features for all three arms; no map identity, absolute coordinates, hidden enemy positions or future labels in prompts','main_task':'professional observed XY trajectory at +0.5,+1,+2 sec; not optimal action','dataset_sha256':hashlib.sha256((DATA/'dataset.json').read_bytes()).hexdigest()}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
 rows=[];texts=[]
 for d in ds:
  samples=json.loads(Path(d['sample_file']).read_text())['samples'];rng=np.random.default_rng(int(d['sha256'][:8],16))
  for i in sorted(rng.choice(len(samples),min(64,len(samples)),replace=False).tolist()):
   s=samples[i];h=np.round(s['h'],3).tolist();c=np.round(s['c'],3).tolist()
   rows.append({'h':h,'c':c,'y':s['y'],'group':d['group'],'map':d['map'],'split':split[d['group']],'demo':d['sha256'],'index':i,'round':s['round'],'tick':s['tick']});texts.append(prompt(h,c))
 np.savez_compressed(OUT/'data.npz',h=np.array([r['h'] for r in rows],np.float32),c=np.array([r['c'] for r in rows],np.float32),y=np.array([r['y'] for r in rows],np.float32),group=np.array([r['group'] for r in rows]),map=np.array([r['map'] for r in rows]),split=np.array([r['split'] for r in rows]))
 (OUT/'rows.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in ['h','c','y']} for r in rows],indent=2));(OUT/'prompts.json').write_text(json.dumps(texts))
 print('samples',len(rows),'eligible',sum(d['samples'] for d in ds),'maps',sorted(set(r['map'] for r in rows)))
 for part in ['train','validation','test']:print(part,{m:sum(r['map']==m and r['split']==part for r in rows) for m in sorted(set(r['map'] for r in rows))})
if __name__=='__main__':main()
