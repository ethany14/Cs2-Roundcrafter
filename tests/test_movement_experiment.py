import importlib.util,json
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('movement_train',ROOT/'experiments/movement/train.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_model_shapes_and_finite_gradients():
 model=m.Model();h=torch.zeros(4,5,8);c=torch.zeros(4,16);out=model(h,c);assert out.shape==(4,6)
 out.square().mean().backward();assert all(torch.isfinite(p.grad).all() for p in model.parameters())
def test_metrics_physical_units():
 y=np.zeros((2,6));p=np.ones((2,6));result=m.metric(p,y);assert abs(result['ADE']-250*2**.5)<1e-5
 assert m.metric(p,y,np.array([False,False]))=={'n':0}
def test_parser_smoke_sample_invariants():
 d=json.loads((ROOT/'outputs/movement/smoke-test.json').read_text());assert d['samples']
 for x in d['samples']:
  assert len(x['h'])==5 and len(x['c'])==16 and len(x['y'])==6
  assert x['h'][-1][:3]==[0,0,0]
  assert 'steamid' not in x and 'winner' not in x

