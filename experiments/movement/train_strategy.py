"""Predict weak observed behaviours, never counterfactual tactical value."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import json,copy,time,hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/strategy'
ARMS=['current','history','history_no_information']
class StrategyModel(nn.Module):
 def __init__(self,size=26):
  super().__init__();self.gru=nn.GRU(size,48,batch_first=True);self.head=nn.Sequential(nn.Linear(48,32),nn.GELU(),nn.Linear(32,3))
 def forward(self,x):return self.head(self.gru(x)[1][-1])
def transform(x,arm):
 x=x.copy()
 if arm=='current':x=np.repeat(x[:,-1:],x.shape[1],axis=1)
 if arm=='history_no_information':x[:,:,18:24]=0
 return x
def scores(y,p):
 pred=p.argmax(1);cm=np.zeros((3,3),int)
 for a,b in zip(y,pred):cm[a,b]+=1
 f1=[2*cm[k,k]/max(1,cm[k,:].sum()+cm[:,k].sum()) for k in range(3)]
 return {'n':len(y),'accuracy':float((pred==y).mean()),'macro_F1':float(np.mean(f1)),'NLL':float(-np.log(np.maximum(1e-8,p[np.arange(len(y)),y])).mean()),'Brier':float(((p-np.eye(3)[y])**2).sum(1).mean()),'confusion':cm.tolist()}
def main():
 start=time.time();old=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text());splits={r['group']:r['split'] for r in old};rows=[]
 for d in json.loads((ROOT/'data/movement/dataset.json').read_text()):
  data=json.loads((ROOT/'data/movement/strategy'/(d['sha256']+'.json')).read_text())
  for r in data['rows']:rows.append({**r,'map':d['map'],'group':d['group'],'demo':d['sha256'],'split':splits[d['group']]})
 (OUT/'rows.json').write_text(json.dumps(rows));h=np.array([r['h'] for r in rows],np.float32);y=np.array([r['label'] for r in rows]);split=np.array([r['split'] for r in rows]);valid=y>=0
 assert np.isfinite(h).all();np.savez_compressed(OUT/'data.npz',h=h,y=y,split=split)
 protocol={'seeds':[7,17,29],'epochs':80,'lr':.001,'batch':256,'selection':'validation NLL','split':'same 19/5/6 series; previously inspected matches, development benchmark only','labels':['approach_or_defuse','limited_net_movement','far_withdrawal'],'label_warning':'weak geometric observations; not retake/wait/save intent or optimality','scenario':'bomb position supplied at plant+2s, not inferred team communication','features':data['names'],'arms':ARMS,'sha256':hashlib.sha256((OUT/'data.npz').read_bytes()).hexdigest()}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2));device='cuda';torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.5);yt=torch.tensor(y,device=device);ids={s:np.flatnonzero((split==s)&valid) for s in ['train','validation','test']};ti=torch.tensor(ids['train'],device=device);result={'protocol':protocol,'rows':len(rows),'labelled':int(valid.sum()),'split_counts':{s:{'all':int((split==s).sum()),'labelled':len(v),'classes':np.bincount(y[v],minlength=3).tolist()} for s,v in ids.items()},'fits':{},'test':{},'by_map':{},'by_series':{}};all_probs={}
 for arm in ARMS:
  x=torch.tensor(transform(h,arm),device=device);probs=[];result['fits'][arm]=[]
  def infer(m,index):
   m.eval()
   with torch.no_grad():return torch.cat([m(x[b]).softmax(-1) for b in np.array_split(index,max(1,int(np.ceil(len(index)/512))))]).cpu().numpy()
  for seed in protocol['seeds']:
   torch.manual_seed(seed);model=StrategyModel(h.shape[-1]).to(device);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01);best=float('inf')
   for epoch in range(80):
    model.train()
    for b in ti[torch.randperm(len(ti),device=device)].split(256):
     opt.zero_grad();loss=nn.functional.cross_entropy(model(x[b]),yt[b]);loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);opt.step()
    score=scores(y[ids['validation']],infer(model,ids['validation']))['NLL']
    if score<best:best=score;state=copy.deepcopy(model.state_dict());best_epoch=epoch+1
   model.load_state_dict(state);probs.append(infer(model,np.arange(len(rows))));torch.save({'state_dict':{k:v.cpu() for k,v in state.items()},'arm':arm,'protocol':protocol},OUT/f'{arm}-{seed}.pt');result['fits'][arm].append({'seed':seed,'epoch':best_epoch,'validation_NLL':best});print(arm,seed,best,flush=True)
  all_probs[arm]=np.mean(probs,0);result['test'][arm]=scores(y[ids['test']],all_probs[arm][ids['test']])
 prior=np.bincount(y[ids['train']],minlength=3)/len(ids['train']);all_probs['training_prior']=np.tile(prior,(len(rows),1))
 # Fixed non-oracle baseline: late/large disadvantage -> withdraw, nearby support -> approach, otherwise hold.
 last=h[:,-1];rule=np.where((last[:,10]>.70)|((last[:,6]-last[:,5])>=.4),2,np.where((last[:,13]>0)|((last[:,5]>=last[:,6])&(last[:,11]<.3)),0,1));all_probs['rule']=np.eye(3)[rule]*.85+.05
 for arm in ['training_prior','rule']:result['test'][arm]=scores(y[ids['test']],all_probs[arm][ids['test']])
 for category in ['map','group']:
  for key in sorted({r[category] for r in rows}):
   mask=np.array([r[category]==key and r['split']=='test' and r['label']>=0 for r in rows]);
   if mask.any():result['by_map' if category=='map' else 'by_series'][key]={a:scores(y[mask],p[mask]) for a,p in all_probs.items()}
 val=ids['validation'];selected=min(ARMS,key=lambda a:scores(y[val],all_probs[a][val])['NLL']);result['selected_by_validation']=selected
 # Abstention threshold is selected exclusively on validation, with >=20 reviewed-label observations.
 thresholds=[]
 for threshold in [.5,.6,.7,.8,.9]:
  keep=all_probs[selected][val].max(1)>=threshold
  if keep.sum()>=20 and (all_probs[selected][val][keep].argmax(1)==y[val][keep]).mean()>=.75:thresholds.append(threshold)
 threshold=min(thresholds) if thresholds else 1.01;test=ids['test'];keep=all_probs[selected][test].max(1)>=threshold;result['abstention']={'threshold':threshold,'validation_target':'75% agreement with weak labels, >=20 windows; not tactical correctness','test_coverage':float(keep.mean()),'test_accuracy':float((all_probs[selected][test][keep].argmax(1)==y[test][keep]).mean()) if keep.any() else None}
 result['seconds']=time.time()-start;result['peak_mb']=torch.cuda.max_memory_allocated()/1024**2;(OUT/'metrics.json').write_text(json.dumps(result,indent=2));np.savez_compressed(OUT/'probabilities.npz',**all_probs);print('DONE',result['test'],flush=True)
if __name__=='__main__':main()
