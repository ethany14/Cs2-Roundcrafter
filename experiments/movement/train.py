"""Local short-horizon behavior cloning experiment; not optimal-action supervision."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import copy,hashlib,json,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'data/movement';OUT=ROOT/'outputs/movement';OUT.mkdir(exist_ok=True)
torch.set_num_threads(4)
DEVICE='cuda' if torch.cuda.is_available() else 'cpu'
if DEVICE=='cuda':torch.cuda.set_per_process_memory_fraction(.5)
class Model(nn.Module):
 def __init__(self):
  super().__init__();self.gru=nn.GRU(8,48,batch_first=True);self.head=nn.Sequential(nn.Linear(64,64),nn.ReLU(),nn.Linear(64,6))
 def forward(self,h,c):
  _,state=self.gru(h);return self.head(torch.cat((state[-1],c),1))
def errors(pred,y):return np.linalg.norm((pred-y).reshape(-1,3,2)*250,axis=2)
def metric(pred,y,mask=None):
 e=errors(pred,y)
 if mask is not None:e=e[mask]
 return {'n':len(e),'ADE':float(e.mean()),'FDE_2s':float(e[:,-1].mean()),'error_05s':float(e[:,0].mean()),'error_1s':float(e[:,1].mean())} if len(e) else {'n':0}
def fit(h,c,y,train,val,seed,epochs=35):
 torch.manual_seed(seed);np.random.seed(seed);m=Model().to(DEVICE);opt=torch.optim.AdamW(m.parameters(),lr=.002,weight_decay=.001)
 tensors=[torch.from_numpy(x).to(DEVICE) for x in (h,c,y)]
 tr=torch.as_tensor(np.flatnonzero(train),device=DEVICE);vi=torch.as_tensor(np.flatnonzero(val),device=DEVICE)
 best=float('inf');state=None;epoch_best=0
 for epoch in range(epochs):
  m.train();order=tr[torch.randperm(len(tr),device=DEVICE)]
  for ids in order.split(2048):
   opt.zero_grad();loss=torch.linalg.vector_norm((m(tensors[0][ids],tensors[1][ids])-tensors[2][ids]).reshape(-1,3,2),dim=2).mean();loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),5);opt.step()
  m.eval()
  with torch.no_grad():v=sum(float(torch.linalg.vector_norm((m(tensors[0][ids],tensors[1][ids])-tensors[2][ids]).reshape(-1,3,2),dim=2).sum()) for ids in vi.split(4096))/(len(vi)*3)
  if v<best:best=v;state=copy.deepcopy(m.state_dict());epoch_best=epoch+1
 m.load_state_dict(state)
 return m,{'seed':seed,'epoch':epoch_best,'validation_ADE':best*250}
def predict(m,h,c):
 with torch.no_grad():return np.concatenate([m(torch.from_numpy(h[i:i+4096]).to(DEVICE),torch.from_numpy(c[i:i+4096]).to(DEVICE)).cpu().numpy() for i in range(0,len(h),4096)])
def main():
 start=time.time();manifest=json.loads((DATA/'dataset.json').read_text());valid=[d for d in manifest if 'sample_file' in d]
 groups=sorted(set(d['group'] for d in valid));nt=max(3,round(len(groups)*.2));nv=max(3,round(len(groups)*.15));split={g:('test' if i<nt else 'validation' if i<nt+nv else 'train') for i,g in enumerate(groups)}
 protocol={'task':'predict observed professional XY displacement at 0.5,1,2 seconds; not optimal decisions','grouping':'one source series archive; exact demo hashes unique','split':split,'seeds':[7,17,29],'epochs':35,'selection':'checkpoint by validation ADE; ensemble all three seeds','history_seconds':2,'sample_stride_seconds':2,'map_features':'no absolute coordinates or map identity; local player-frame motion and teammate offsets','limitations':['No terrain or visibility rays in this baseline','No hidden enemy positions','Only windows alive for entire history/future; excludes death outcomes','No prediction of kills, utility or winning counterfactuals'],'dataset_sha256':hashlib.sha256((DATA/'dataset.json').read_bytes()).hexdigest()}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
 hs=[];cs=[];ys=[];gs=[];maps=[]
 seen=set()
 for d in valid:
  assert d['sha256'] not in seen;seen.add(d['sha256']);s=json.loads(Path(d['sample_file']).read_text())['samples']
  hs.extend(x['h'] for x in s);cs.extend(x['c'] for x in s);ys.extend(x['y'] for x in s);gs.extend([d['group']]*len(s));maps.extend([d['map']]*len(s))
 h,c,y=[np.array(x,dtype=np.float32) for x in (hs,cs,ys)];g=np.array(gs);maps=np.array(maps);del hs,cs,ys,gs
 assert np.isfinite(h).all() and np.isfinite(c).all() and np.isfinite(y).all()
 tr=np.array([split[x]=='train' for x in g]);va=np.array([split[x]=='validation' for x in g]);te=np.array([split[x]=='test' for x in g])
 # Last half-second velocity, extrapolated at the three horizons.
 velocity=(-h[:,-2,:2,None]*np.array([1,2,4],dtype=np.float32)).transpose(0,2,1).reshape(-1,6)
 decay=min(np.linspace(0,1,21),key=lambda a:errors(a*velocity[va],y[va]).mean())
 preds=[];fits=[]
 for seed in protocol['seeds']:
  m,info=fit(h,c,y,tr,va,seed);preds.append(predict(m,h[te],c[te]));fits.append(info)
  torch.save({'state_dict':m.state_dict(),'protocol':protocol,'selection':info},OUT/f'movement-seed-{seed}.pt');print('fit',info,flush=True)
 pred=np.mean(preds,axis=0);yt=y[te];gt=g[te];mt=maps[te];moving=np.linalg.norm(yt[:,-2:],axis=1)*250>100
 variants={'stationary':np.zeros_like(yt),'constant_velocity':velocity[te],'validation_tuned_velocity':velocity[te]*decay,'gru_ensemble':pred}
 result={'device':DEVICE,'gpu':torch.cuda.get_device_name(0) if DEVICE=='cuda' else None,'samples':len(y),'series':len(groups),'maps':sorted(set(maps.tolist())),'split_samples':{s:int(sum(np.array([split[x]==s for x in g]))) for s in ['train','validation','test']},'split_series':{s:sum(v==s for v in split.values()) for s in ['train','validation','test']},'fits':fits,'velocity_factor':float(decay),'overall':{name:metric(v,yt) for name,v in variants.items()},'moving_only':{name:metric(v,yt,moving) for name,v in variants.items()},'by_map':{},'by_series':{}}
 for kind,values,key in [('by_map',mt,mt),('by_series',gt,gt)]:
  for name in sorted(set(values.tolist())):
   mask=key==name;result[kind][name]={k:metric(v[mask],yt[mask]) for k,v in variants.items()}
 # Paired series bootstrap: independent unit is a match, not overlapping player frames.
 improvement=np.array([v['validation_tuned_velocity']['ADE']-v['gru_ensemble']['ADE'] for v in result['by_series'].values()]);rng=np.random.default_rng(42)
 ci=np.quantile(rng.choice(improvement,(5000,len(improvement)),replace=True).mean(1),[.025,.975]);result['series_macro_ADE_improvement_vs_tuned_velocity']={'mean':float(improvement.mean()),'bootstrap_95pct':ci.tolist(),'test_series':len(improvement)}
 # Held-out-map transfer: remove alphabetically first sufficiently represented map from fitting/validation;
 # evaluate ONLY its fresh test-series frames. Main model above still trains all training maps.
 candidates=[name for name in sorted(set(maps.tolist())) if ((maps==name)&te).sum()>500 and ((maps==name)&tr).sum()>1000]
 if candidates:
  held=candidates[0];m,info=fit(h,c,y,tr&(maps!=held),va&(maps!=held),7);mask=te&(maps==held);pp=predict(m,h[mask],c[mask]);result['unseen_map_probe']={'map':held,'fit':info,'model':metric(pp,y[mask]),'tuned_velocity':metric(velocity[mask]*decay,y[mask]),'test_series':len(set(g[mask].tolist())),'note':'single-seed secondary diagnostic; no held-map samples used for model fitting/epoch selection; velocity factor from main validation'}
  torch.save({'state_dict':m.state_dict(),'held_map':held},OUT/'unseen-map-probe.pt')
 result['seconds']=time.time()-start;result['peak_gpu_allocated_mb']=torch.cuda.max_memory_allocated()/1024**2 if DEVICE=='cuda' else 0
 (OUT/'metrics.json').write_text(json.dumps(result,indent=2));np.savez_compressed(OUT/'test_predictions.npz',prediction=pred,target=yt,group=gt,map=mt)
 print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
