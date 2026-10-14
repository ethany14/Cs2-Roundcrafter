"""Offline joint inference; no deployment or optimal-action claims."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from train_joint import Model,TYPES,OUT,OLD

def predict(h,c,j):
 arrays=[np.asarray(x,dtype=np.float32) for x in [h,c,j]]
 if [x.shape for x in arrays]!=[(5,8),(16,),(5,26)] or any(not np.isfinite(x).all() for x in arrays):raise ValueError('Expected finite h[5,8], c[16], j[5,26]')
 tensors=[torch.from_numpy(x).unsqueeze(0) for x in arrays];moves=[];probs=[]
 for seed in [7,17,29]:
  ck=torch.load(OUT/f'joint-{seed}.pt',map_location='cpu',weights_only=True);m=Model('joint',ck['extra']);m.load_state_dict(ck['state_dict']);m.eval()
  with torch.no_grad():p,a=m(*tensors);moves.append(p.numpy());probs.append(a.softmax(-1).numpy())
 path=np.mean(moves,0).reshape(3,2)*250;prob=np.mean(probs,0)[0];metrics=json.loads((OUT/'metrics.json').read_text())
 return {'status':'experimental_behavior_prediction_not_optimal_decision','horizons_seconds':[.5,1,2],'local_forward_right_game_units':path.tolist(),'actions':{name:({'supported':False,'reason':'no positive training examples'} if metrics['actions'][name]['train_positive']==0 else {'supported':True,'probability_within_2s':float(1-prob[k,0]),'first_time_bin_probabilities':dict(zip(['none','0_to_05s','05_to_1s','1_to_2s'],prob[k].tolist()))}) for k,name in enumerate(TYPES)},'limitations':['No hidden enemies or enemy gunshot audibility','No terrain/utility-effect feasibility checks','Trajectory and action heads do not ensure physical consistency']}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--sample-index',type=int);parser.add_argument('--input');parser.add_argument('--output',required=True);args=parser.parse_args()
 if args.input:data=json.loads(Path(args.input).read_text());result=predict(data['h'],data['c'],data['j'])
 elif args.sample_index is not None:
  old=np.load(OLD/'data.npz');new=np.load(OUT/'data.npz');i=args.sample_index;result=predict(old['h'][i],old['c'][i],new['j'][i]);result['sample_index']=i
 else:parser.error('Specify --input or --sample-index')
 Path(args.output).write_text(json.dumps(result,indent=2));print('Saved',args.output)
if __name__=='__main__':main()
