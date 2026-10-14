"""Local registered-sample prediction with the experimental environmental model."""
import argparse,json,hashlib
import numpy as np
import torch
from train_environment import ROOT,OUT
from train_joint import Model,TYPES

def predict(index):
 base=np.load(ROOT/'outputs/movement/comparison/data.npz');joint=np.load(ROOT/'outputs/movement/joint/data.npz');env=np.load(OUT/'features.npy')
 if not 0<=index<len(env):raise ValueError('Unknown sample index')
 tensors=[torch.from_numpy(x.astype(np.float32)).unsqueeze(0) for x in [base['h'][index],np.r_[base['c'][index],env[index]],joint['j'][index]]];moves=[];actions=[]
 for seed in [7,17,29]:
  ck=torch.load(OUT/f'environment_joint-{seed}.pt',map_location='cpu',weights_only=True)
  if ck['protocol']['features_sha256']!=hashlib.sha256((OUT/'features.npy').read_bytes()).hexdigest():raise ValueError('Features changed since training')
  model=Model('joint',ck['extra'],ck['context_dim']);model.load_state_dict(ck['state_dict']);model.eval()
  with torch.no_grad():p,a=model(*tensors)
  moves.append(p.numpy());actions.append(a.softmax(-1).numpy())
 prob=np.mean(actions,0)[0]
 return {'sample_index':index,'status':'experimental_behavior_prediction_not_optimal_decision','horizons_seconds':[.5,1,2],'local_forward_right_game_units':(np.mean(moves,0).reshape(3,2)*250).tolist(),'actions':{name:({'supported':False,'reason':'no positive training examples'} if not (joint['target'][base['split']=='train',k]>0).any() else {'supported':True,'probability_within_2s':float(1-prob[k,0]),'first_time_bin_probabilities':dict(zip(['none','0_to_05s','05_to_1s','1_to_2s'],prob[k].tolist()))}) for k,name in enumerate(TYPES)},'limitations':['Sound candidates are not confirmed hearing.','Trajectory is not constrained to navigation or weapon movement mechanics.','No validated wall damage or demonstrated optimal tactical choices.']}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--sample-index',type=int,required=True);parser.add_argument('--output',required=True);args=parser.parse_args();from pathlib import Path
 Path(args.output).write_text(json.dumps(predict(args.sample_index),indent=2));print('Saved',args.output)
