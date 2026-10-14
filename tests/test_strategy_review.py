import json
import numpy as np
from cs2_agent.casebook import ROOT
from cs2_agent.strategy import inspect_sample
DATA=ROOT/'outputs/movement/strategy/review'
def test_review_roster_and_economy():
 index=json.loads((DATA/'index.json').read_text());assert len(index)==21
 for case in index:
  d=json.loads((DATA/(case['id']+'.json')).read_text());team=d['team'];assert len(team)==5 and all(p['side']=='CT' for p in team);assert sum(p['self'] for p in team)==1
  assert d['economy']['team_cash']==sum(p['cash'] for p in team)
  assert d['economy']['alive_equipment']==sum(p['equipment'] for p in team if p['alive'])
  assert d['economy']['loss_bonus'] is None and d['economy']['next_round_income'] is None
  assert all(len(p['position'])==3 and np.isfinite(p['position']).all() for p in team)
  assert not ({'winner','label','future','enemies'}&set(d))
def test_observer_data_separate_from_agent():
 case=json.loads((DATA/'index.json').read_text())[0];observer=json.loads((DATA/(case['id']+'-observer.json')).read_text());assert observer['mode']=='spectator_only_not_player_knowledge'
 d=inspect_sample(case['sample_index']);assert 'team_economy' in d and all(p['side']=='CT' for p in d['current_team']);assert 'enemies' not in d
