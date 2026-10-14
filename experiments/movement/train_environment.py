"""Matched exploratory comparison: existing joint model + causal current context."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
import copy,json,time,hashlib
from pathlib import Path
import numpy as np
import torch
from torch import nn
from train_joint import Model,ade,stats,TYPES
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/movement/environment'

def main():
 start=time.time();base=np.load(ROOT/'outputs/movement/comparison/data.npz');joint=np.load(ROOT/'outputs/movement/joint/data.npz');env=np.load(OUT/'features.npy')
 assert env.shape==(len(base['h']),42) and np.isfinite(env).all()
 split=base['split'];masks={k:split==k for k in ['train','validation','test']};device='cuda';torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.5)
 protocol={'seeds':[7,17,29],'epochs':100,'batch':256,'lr':.001,'weight_decay':.01,'action_loss_weight':.15,'selection':'minimum validation movement ADE','split':'fixed 19/5/6 series; 4928 samples, all 7 maps; test previously inspected, exploratory only','features_sha256':hashlib.sha256((OUT/'features.npy').read_bytes()).hexdigest(),'context':'42 current environmental features appended to 16 context fields; not repeated into historical frames','limits':['sound support candidates, not confirmed audibility','spotted flags approximate visibility','static geometry, dynamic state unknown','no validated penetration damage','no tactical optimality labels']}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
 ids={k:torch.tensor(np.flatnonzero(v),device=device) for k,v in masks.items()};y=base['y'];target=joint['target'];preds={};probabilities={};fits={}
 for arm in ['joint_baseline','environment_joint']:
  c=base['c'] if arm=='joint_baseline' else np.concatenate([base['c'],env],1)
  tensors=[torch.from_numpy(x).to(device) for x in [base['h'],c,joint['j'],y,target]]
  def infer(model,index):
   model.eval()
   with torch.no_grad():
    pairs=[model(*[x[b] for x in tensors[:3]]) for b in index.split(512)]
   return torch.cat([p[0] for p in pairs]).cpu().numpy(),torch.cat([p[1].softmax(-1) for p in pairs]).cpu().numpy()
  pp=[];aa=[];fits[arm]=[]
  for seed in protocol['seeds']:
   stamp=time.time();torch.manual_seed(seed);model=Model('joint',joint['j'].shape[-1],c.shape[-1]).to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01);best=float('inf')
   for epoch in range(100):
    model.train();order=ids['train'][torch.randperm(len(ids['train']),device=device)]
    for b in order.split(256):
     optimizer.zero_grad();pm,pa=model(*[x[b] for x in tensors[:3]]);loss=torch.linalg.vector_norm((pm-tensors[3][b]).reshape(-1,3,2),dim=-1).mean()+.15*nn.functional.cross_entropy(pa.reshape(-1,4),tensors[4][b].reshape(-1));loss.backward();nn.utils.clip_grad_norm_(model.parameters(),5);optimizer.step()
    score=ade(infer(model,ids['validation'])[0],y[masks['validation']])
    if score<best:best=score;state=copy.deepcopy(model.state_dict());best_epoch=epoch+1
   model.load_state_dict(state);p,a=infer(model,ids['test']);pp.append(p);aa.append(a);fits[arm].append({'seed':seed,'epoch':best_epoch,'validation_ADE':best,'test_ADE':ade(p,y[masks['test']]),'seconds':time.time()-stamp})
   torch.save({'state_dict':{k:v.cpu() for k,v in state.items()},'arm':'joint','extra':joint['j'].shape[-1],'context_dim':c.shape[-1],'protocol':protocol},OUT/f'{arm}-{seed}.pt');print(arm,fits[arm][-1],flush=True)
  preds[arm]=np.mean(pp,0);probabilities[arm]=np.mean(aa,0)
 te=masks['test'];truth=target[te];result={'protocol':protocol,'fits':fits,'ADE':{k:ade(v,y[te]) for k,v in preds.items()},'actions':{},'by_map':{},'by_series':{},'seconds':time.time()-start,'peak_mb':torch.cuda.max_memory_allocated()/1024**2}
 for k,name in enumerate(TYPES):
  yes=truth[:,k]>0
  result['actions'][name]={arm:stats(yes,1-p[:,k,0]) for arm,p in probabilities.items()}
  result['actions'][name]['repeat_recent_action']=stats(yes,(joint['j'][te,-1,18+k]>0).astype(float))
 for cat,label in [('by_map',base['map'][te]),('by_series',base['group'][te])]:
  result[cat]={str(key):{arm:ade(p[label==key],y[te][label==key]) for arm,p in preds.items()} for key in sorted(set(label))}
 values=np.array([x['joint_baseline']-x['environment_joint'] for x in result['by_series'].values()]);rng=np.random.default_rng(42);result['paired_series_improvement']={'mean':float(values.mean()),'ci95':np.quantile(rng.choice(values,(10000,len(values)),replace=True).mean(1),[.025,.975]).tolist()}
 (OUT/'metrics.json').write_text(json.dumps(result,indent=2));np.savez_compressed(OUT/'test-predictions.npz',**preds,**{k+'_actions':v for k,v in probabilities.items()});print('DONE',result['ADE'],flush=True)
if __name__=='__main__':main()
