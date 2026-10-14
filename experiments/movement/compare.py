"""Three-arm frozen-Qwen experiment. Run only after feature extraction completes."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import json,time,copy,hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/comparison'
torch.set_num_threads(4)
class Net(nn.Module):
 def __init__(self,arm,dim=2560):
  super().__init__();self.arm=arm
  if arm!='qwen_adapter':self.gru=nn.GRU(8,48,batch_first=True)
  if arm!='numeric':self.adapter=nn.Sequential(nn.Linear(dim,64),nn.GELU(),nn.Dropout(.1))
  width={'numeric':64,'qwen_adapter':64,'fusion':128}[arm]
  self.head=nn.Sequential(nn.Linear(width,64),nn.GELU(),nn.Linear(64,6))
 def forward(self,h,c,e):
  parts=[]
  if self.arm!='qwen_adapter':parts.append(torch.cat((self.gru(h)[1][-1],c),1))
  if self.arm!='numeric':parts.append(self.adapter(e))
  return self.head(torch.cat(parts,1))
def distance(pred,y):return np.linalg.norm((pred-y).reshape(-1,3,2),axis=2)*250
def metrics(p,y):
 e=distance(p,y);return {'n':len(y),'ADE':float(e.mean()),'error_05s':float(e[:,0].mean()),'error_1s':float(e[:,1].mean()),'FDE_2s':float(e[:,2].mean())} if len(y) else {'n':0}
def bootstrap(v):
 rng=np.random.default_rng(42);a=np.array(v);ci=np.quantile(rng.choice(a,(10000,len(a)),replace=True).mean(1),[.025,.975]);return {'mean':float(a.mean()),'ci95':ci.tolist(),'series':len(a)}
def main():
 start=time.time();protocol=json.loads((OUT/'protocol.json').read_text());meta=json.loads((OUT/'qwen-metadata.json').read_text());assert meta['prompts_sha256']==hashlib.sha256((OUT/'prompts.json').read_bytes()).hexdigest()
 data=np.load(OUT/'data.npz');h,c,y=[data[k] for k in ['h','c','y']];e=np.load(OUT/'qwen-features.npy');assert len(h)==len(e) and np.isfinite(e).all()
 split=data['split'];tr=split=='train';va=split=='validation';te=split=='test';groups=data['group'];maps=data['map']
 assert not(set(groups[tr])&set(groups[va])) and not(set(groups[tr])&set(groups[te])) and not(set(groups[va])&set(groups[te]))
 mean=e[tr].mean(0);std=e[tr].std(0).clip(.01);e=((e-mean)/std).astype(np.float32);np.savez(OUT/'embedding-scaler.npz',mean=mean,std=std)
 device='cuda' if torch.cuda.is_available() else 'cpu'
 if device=='cuda':torch.cuda.set_per_process_memory_fraction(.5)
 tensors=[torch.from_numpy(x).to(device) for x in [h,c,e,y]];ti=torch.tensor(np.flatnonzero(tr),device=device);vi=torch.tensor(np.flatnonzero(va),device=device);testi=torch.tensor(np.flatnonzero(te),device=device)
 def inference(model,ids):
  model.eval()
  with torch.no_grad():return torch.cat([model(*[x[b] for x in tensors[:3]]) for b in ids.split(512)]).cpu().numpy()
 records={};predictions={};seeds_predictions={}
 for arm in ['numeric','qwen_adapter','fusion']:
  ps=[];info=[]
  for seed in protocol['seeds']:
   stamp=time.time();torch.manual_seed(seed);model=Net(arm,e.shape[1]).to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01);best=float('inf');state=None
   for epoch in range(protocol['epochs']):
    model.train();order=ti[torch.randperm(len(ti),device=device)]
    for b in order.split(protocol['batch_size']):
     optimizer.zero_grad();out=model(*[x[b] for x in tensors[:3]]);loss=torch.linalg.vector_norm((out-tensors[3][b]).reshape(-1,3,2),dim=2).mean();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
    score=metrics(inference(model,vi),y[va])['ADE']
    if score<best:best=score;best_epoch=epoch+1;state=copy.deepcopy(model.state_dict())
   model.load_state_dict(state);pred=inference(model,testi);ps.append(pred)
   row={'seed':seed,'best_epoch':best_epoch,'validation_ADE':best,'test':metrics(pred,y[te]),'seconds':time.time()-stamp,'parameters':sum(x.numel() for x in model.parameters())};info.append(row)
   torch.save({'state_dict':{k:v.cpu() for k,v in state.items()},'arm':arm,'embedding_dim':e.shape[1],'protocol':protocol,'best_epoch':best_epoch,'validation_ADE':best},OUT/f'{arm}-{seed}.pt')
   print(arm,json.dumps({k:v for k,v in row.items() if k!='test'}),flush=True)
  records[arm]=info;predictions[arm]=np.mean(ps,axis=0);seeds_predictions[arm]=np.stack(ps)
 velocity=(-h[:,-2,:2,None]*np.array([1,2,4],np.float32)).transpose(0,2,1).reshape(-1,6);factor=float(min(np.linspace(0,1,21),key=lambda a:metrics(a*velocity[va],y[va])['ADE']))
 predictions.update(stationary=np.zeros_like(y[te]),constant_velocity=velocity[te],tuned_velocity=velocity[te]*factor)
 yt=y[te];gt=groups[te];mt=maps[te];moving=np.linalg.norm(yt[:,-2:],axis=1)*250>100
 result={'protocol':protocol,'samples':len(y),'split_samples':{s:int((split==s).sum()) for s in ['train','validation','test']},'split_series':{s:len(set(groups[split==s].tolist())) for s in ['train','validation','test']},'fits':records,'overall':{k:metrics(p,yt) for k,p in predictions.items()},'moving_only':{k:metrics(p[moving],yt[moving]) for k,p in predictions.items()},'by_map':{},'by_series':{},'tuned_velocity_factor':factor,'gpu':torch.cuda.get_device_name(0) if device=='cuda' else 'cpu'}
 for category,labels in [('by_map',mt),('by_series',gt)]:
  for label in sorted(set(labels.tolist())):
   mask=labels==label;result[category][label]={k:metrics(p[mask],yt[mask]) for k,p in predictions.items()}
 result['paired_series_improvement']={}
 for arm,baseline in [('qwen_adapter','numeric'),('fusion','numeric'),('numeric','tuned_velocity'),('fusion','tuned_velocity')]:
  result['paired_series_improvement'][arm+'_vs_'+baseline]=bootstrap([r[baseline]['ADE']-r[arm]['ADE'] for r in result['by_series'].values()])
 # Warm in-memory batch latency; excludes tokenization and Qwen feature extraction.
 latency={}
 for arm in ['numeric','qwen_adapter','fusion']:
  ck=torch.load(OUT/f'{arm}-7.pt',map_location=device,weights_only=True);m=Net(arm,e.shape[1]).to(device);m.load_state_dict(ck['state_dict']);m.eval();inputs=[x[testi[:1]] for x in tensors[:3]]
  with torch.no_grad():
   for _ in range(10):m(*inputs)
   if device=='cuda':torch.cuda.synchronize()
   t=time.perf_counter()
   for _ in range(100):m(*inputs)
   if device=='cuda':torch.cuda.synchronize()
  latency[arm]=(time.perf_counter()-t)*10
 result['cached_feature_single_sample_ms']=latency;result['training_seconds']=time.time()-start;result['training_peak_gpu_mb']=torch.cuda.max_memory_allocated()/1024**2 if device=='cuda' else 0
 (OUT/'metrics.json').write_text(json.dumps(result,indent=2));np.savez_compressed(OUT/'test-predictions.npz',**predictions,target=yt,group=gt,map=mt,**{k+'_seeds':v for k,v in seeds_predictions.items()});print('DONE',json.dumps(result['overall']),flush=True)
if __name__=='__main__':main()
