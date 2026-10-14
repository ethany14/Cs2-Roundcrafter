import importlib.util,json
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
def module(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'experiments/movement'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_series_and_demo_partitions_do_not_overlap():
 rows=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text())
 for key in ['group','demo']:
  sets=[{r[key] for r in rows if r['split']==s} for s in ['train','validation','test']]
  assert not sets[0]&sets[1] and not sets[0]&sets[2] and not sets[1]&sets[2]
 assert len({(r['demo'],r['index']) for r in rows})==len(rows)
 assert all(len({r['map'] for r in rows if r['split']==s})==7 for s in ['train','validation','test'])

def test_prompt_exact_feature_roundtrip_and_no_labels():
 mod=module('prepare_comparison');data=np.load(ROOT/'outputs/movement/comparison/data.npz');texts=json.loads((ROOT/'outputs/movement/comparison/prompts.json').read_text())
 for i in [0,200,len(texts)-1]:
  lines=texts[i].splitlines();np.testing.assert_allclose(json.loads(lines[1]),data['h'][i],atol=1e-6);np.testing.assert_allclose(json.loads(lines[3]),data['c'][i],atol=1e-6)
  assert 'winner' not in texts[i] and 'steamid' not in texts[i]
  # Prompt function accepts only the two current/past feature inputs, never targets.
  assert mod.prompt.__code__.co_argcount==2

def test_all_arms_gradients_and_shapes():
 mod=module('compare')
 for arm in ['numeric','qwen_adapter','fusion']:
  model=mod.Net(arm,12);out=model(torch.randn(3,5,8),torch.randn(3,16),torch.randn(3,12));assert out.shape==(3,6)
  torch.linalg.vector_norm(out.reshape(-1,3,2),dim=2).mean().backward();assert all(torch.isfinite(p.grad).all() for p in model.parameters())

def test_metric_units_and_bootstrap_direction():
 mod=module('compare');x=np.tile([1,0],(2,3));assert mod.metrics(x,np.zeros_like(x))['ADE']==250
 b=mod.bootstrap([2,2,2]);assert b['mean']==2 and b['ci95']==[2,2]
