import argparse,json
from pathlib import Path
import numpy as np
import torch
from train_strategy import StrategyModel,transform,OUT
def predict(h):
 h=np.asarray(h,dtype=np.float32)
 if h.shape!=(7,26) or not np.isfinite(h).all():raise ValueError('Expected finite history [7,26]')
 metrics=json.loads((OUT/'metrics.json').read_text());arm=metrics['selected_by_validation'];x=torch.from_numpy(transform(h[None],arm));probs=[];torch.set_num_threads(4)
 for seed in [7,17,29]:
  ck=torch.load(OUT/f'{arm}-{seed}.pt',map_location='cpu',weights_only=True);m=StrategyModel();m.load_state_dict(ck['state_dict']);m.eval()
  with torch.no_grad():probs.append(m(x).softmax(-1).numpy()[0])
 p=np.mean(probs,0)
 return {'status':'weak_behaviour_prediction_not_tactical_value','model':arm,'probabilities':dict(zip(metrics['protocol']['labels'],p.tolist())),'abstain':bool(p.max()<metrics['abstention']['threshold'])}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--sample-index',type=int);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 if args.input:h=json.loads(args.input.read_text())['h']
 elif args.sample_index is not None:
  data=np.load(OUT/'data.npz')['h']
  if not 0<=args.sample_index<len(data):raise ValueError('Unknown sample')
  h=data[args.sample_index]
 else:p.error('Provide --input or --sample-index')
 args.output.write_text(json.dumps(predict(h),indent=2));print('Saved',args.output)
