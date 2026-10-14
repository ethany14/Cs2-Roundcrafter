import importlib.util
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('train_joint',ROOT/'experiments/movement/train_joint.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def test_average_precision_tied_scores():
 assert m.ap(np.array([1,0,1,0]),np.ones(4))==.5
 assert m.ap(np.zeros(4),np.ones(4)) is None
 assert m.ap(np.array([1,1,0]),np.array([3,2,1]))==1

def test_joint_head_and_gradient():
 model=m.Model('joint',26);p,a=model(torch.randn(2,5,8),torch.randn(2,16),torch.randn(2,5,26));assert p.shape==(2,6);assert a.shape==(2,6,4)
 loss=p.square().mean()+torch.nn.functional.cross_entropy(a.reshape(-1,4),torch.zeros(12,dtype=torch.long));loss.backward();assert all(torch.isfinite(x.grad).all() for x in model.parameters())

def test_environment_context_head():
 model=m.Model('joint',26,58);p,a=model(torch.randn(2,5,8),torch.randn(2,58),torch.randn(2,5,26));assert p.shape==(2,6) and a.shape==(2,6,4)
