import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import json,time,copy
from pathlib import Path
import numpy as np
import torch
from torch import nn
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/joint';OLD=ROOT/'outputs/movement/comparison';TYPES=['fire','smoke','flash','he','incendiary','decoy']
torch.set_num_threads(4)
class Model(nn.Module):
 def __init__(self,arm,extra,context_dim=16):
  super().__init__();self.arm=arm;self.gru=nn.GRU(8+(extra if arm!='original' else 0),48,batch_first=True);self.body=nn.Sequential(nn.Linear(48+context_dim,64),nn.GELU());self.move=nn.Linear(64,6)
  if arm=='joint':self.action=nn.Linear(64,24)
 def forward(self,h,c,j):
  seq=h if self.arm=='original' else torch.cat((h,j),-1);z=self.body(torch.cat((self.gru(seq)[1][-1],c),1));return self.move(z),self.action(z).reshape(-1,6,4) if self.arm=='joint' else None

def ade(p,y):return float(np.linalg.norm((p-y).reshape(-1,3,2)*250,axis=2).mean())
def ap(y,p):
 if not y.sum():return None
 order=np.argsort(-p,kind='stable');ys=y[order];ps=p[order];ends=np.r_[np.flatnonzero(np.diff(ps)!=0),len(ps)-1];tp=np.cumsum(ys)[ends];return float(np.sum(np.diff(np.r_[0,tp])*tp/(ends+1))/y.sum())
def stats(y,p):return {'n':len(y),'positive':int(y.sum()),'prevalence':float(y.mean()),'Brier':float(((p-y)**2).mean()),'AP':ap(y,p)}
def main():
 start=time.time();data=np.load(OLD/'data.npz');rows=json.loads((OLD/'rows.json').read_text());cache={};js=[];ys=[];audit=[]
 for row in rows:
  demo=row['demo']
  if demo not in cache:
   d=json.loads((ROOT/'data/movement/joint'/f'{demo}.json').read_text());cache[demo]={x['index']:x for x in d['rows']};audit.append(d['audit'])
  d=cache[demo][row['index']];i=len(js);assert d['tick']==row['tick'];np.testing.assert_allclose(np.round(d['base']['h'],3),data['h'][i],atol=1e-6);np.testing.assert_allclose(np.round(d['base']['c'],3),data['c'][i],atol=1e-6);np.testing.assert_allclose(d['base']['y'],data['y'][i],atol=1e-6);js.append(d['j']);binary=np.array(d['actions']).reshape(3,6);ys.append([int(np.flatnonzero(binary[:,k])[0]+1) if binary[:,k].any() else 0 for k in range(6)])
 h,c,y=data['h'],data['c'],data['y'];j=np.array(js,np.float32);target=np.array(ys,np.int64);assert np.isfinite(j).all();split=data['split'];tr=split=='train';va=split=='validation';te=split=='test'
 protocol={'seeds':[7,17,29],'epochs':100,'lr':.001,'weight_decay':.01,'batch':256,'action_loss_weight':.15,'checkpoint':'validation movement ADE only, identical rule across arms; action outcomes secondary','split':'exact same 4928 samples and 19/5/6 series as prior comparison; already inspected test, exploratory development benchmark','actions':TYPES,'timing':'first event in (0,.5],(.5,1],(1,2] seconds or none; multi-action categories allowed','extra_features':j.shape[-1],'source':'self fire/throw/hurt, own weapon and inventory, causal prefix only; no enemy firing events','limitations':['survivor windows only','no sound propagation or full enemy perception','no geometry or active grenade effect fields','known old test set; not confirmatory']}
 (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2));np.savez_compressed(OUT/'data.npz',j=j,target=target)
 device='cuda';torch.cuda.set_per_process_memory_fraction(.5);ts=[torch.from_numpy(x).to(device) for x in [h,c,j,y,target]];ti=torch.as_tensor(np.flatnonzero(tr),device=device);vi=torch.as_tensor(np.flatnonzero(va),device=device);tei=torch.as_tensor(np.flatnonzero(te),device=device)
 def infer(m,ids):
  m.eval()
  with torch.no_grad():
   pairs=[m(*[x[b] for x in ts[:3]]) for b in ids.split(512)];return torch.cat([x[0] for x in pairs]).cpu().numpy(),torch.cat([x[1].softmax(-1) for x in pairs]).cpu().numpy() if m.arm=='joint' else None
 preds={};fits={};probs=[]
 for arm in ['original','enriched_move','joint']:
  pp=[];fits[arm]=[]
  for seed in protocol['seeds']:
   stamp=time.time();torch.manual_seed(seed);m=Model(arm,j.shape[-1]).to(device);opt=torch.optim.AdamW(m.parameters(),lr=.001,weight_decay=.01);best=float('inf')
   for epoch in range(100):
    m.train();order=ti[torch.randperm(len(ti),device=device)]
    for b in order.split(256):
     opt.zero_grad();pm,pa=m(*[x[b] for x in ts[:3]]);loss=torch.linalg.vector_norm((pm-ts[3][b]).reshape(-1,3,2),dim=-1).mean()
     if pa is not None:loss=loss+.15*nn.functional.cross_entropy(pa.reshape(-1,4),ts[4][b].reshape(-1))
     loss.backward();nn.utils.clip_grad_norm_(m.parameters(),5);opt.step()
    score=ade(infer(m,vi)[0],y[va])
    if score<best:best=score;state=copy.deepcopy(m.state_dict());best_epoch=epoch+1
   m.load_state_dict(state);p,prob=infer(m,tei);pp.append(p)
   if prob is not None:probs.append(prob)
   fits[arm].append({'seed':seed,'epoch':best_epoch,'validation_ADE':best,'test_ADE':ade(p,y[te]),'seconds':time.time()-stamp})
   torch.save({'state_dict':{k:v.cpu() for k,v in state.items()},'arm':arm,'extra':j.shape[-1],'protocol':protocol},OUT/f'{arm}-{seed}.pt');print(arm,fits[arm][-1],flush=True)
  preds[arm]=np.mean(pp,0)
 prob=np.mean(probs,0);actual=target[te];prior=np.stack([np.bincount(target[tr,k],minlength=4)/tr.sum() for k in range(6)]);action={}
 for k,name in enumerate(TYPES):
  yes=actual[:,k]>0;pv=1-prob[:,k,0];constant=np.full(len(yes),1-prior[k,0]);past=j[te,-1,18+k]>0
  action[name]={'model':stats(yes,pv),'training_prior':stats(yes,constant),'repeat_recent_action':stats(yes,past.astype(float)),'train_positive':int((target[tr,k]>0).sum()),'validation_positive':int((target[va,k]>0).sum()),'first_bin_accuracy_given_event':float((prob[yes,k,1:].argmax(1)+1==actual[yes,k]).mean()) if yes.any() else None,'prior_first_bin_accuracy_given_event':float((prior[k,1:].argmax()+1==actual[yes,k]).mean()) if yes.any() else None}
 result={'protocol':protocol,'fits':fits,'ADE':{k:ade(v,y[te]) for k,v in preds.items()},'moving_ADE':{},'by_map':{},'by_series':{},'actions':action,'seconds':time.time()-start,'peak_mb':torch.cuda.max_memory_allocated()/1024**2,'audit':{k:sum(a[k] for a in audit) for k in audit[0]}}
 moving=np.linalg.norm(y[te,-2:],axis=1)*250>100
 result['moving_ADE']={k:ade(v[moving],y[te][moving]) for k,v in preds.items()}
 for category,labels in [('by_map',data['map'][te]),('by_series',data['group'][te])]:
  for name in sorted(set(labels.tolist())):
   mask=labels==name;result[category][name]={k:ade(v[mask],y[te][mask]) for k,v in preds.items()}
 rng=np.random.default_rng(42);vals=np.array([v['original']-v['joint'] for v in result['by_series'].values()]);result['paired_improvement']={'mean':float(vals.mean()),'ci95':np.quantile(rng.choice(vals,(10000,len(vals)),replace=True).mean(1),[.025,.975]).tolist()}
 (OUT/'metrics.json').write_text(json.dumps(result,indent=2));np.savez_compressed(OUT/'test-predictions.npz',**preds,action_probabilities=prob,action_target=actual,movement_target=y[te]);print('DONE',result['ADE'],flush=True)
if __name__=='__main__':main()
