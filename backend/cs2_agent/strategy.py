"""Conditional post-plant study. Candidate conditions are rules, not learned action value."""
import json
from pathlib import Path
from .casebook import ROOT
DIRECTORY=ROOT/'outputs/movement/strategy'
def candidates(features):
 f=features;kit=bool(f['kit']);age=f['bomb_age']*40;distance=f['bomb_distance_lower_bound']*6000
 return {'scenario':{'bomb_position':'explicitly supplied, not reconstructed communication','nominal_bomb_seconds_remaining':max(0,40-age),'timer_assumption_seconds':40,'distance_units':distance,'straight_line_travel_proxy_seconds':distance/250,'travel_assumption':'250 units/s, ignores navigation, elevation, clearing and fighting; not a route feasibility proof','defuse_seconds_assumption':5 if kit else 10,'defuse_kit_known':bool(f['kit_known'])},'evidence':{'ct_alive':round(f['ct_alive']*5),'t_alive':round(f['t_alive']*5),'nearest_teammate_distance_units':f['mate_nearest']*6000,'teammates_within_800_of_bomb':round(f['mates_near_bomb']*4),'own_equipment_value':f['equipment']*10000,'last_seen_age_seconds':f['seen_age']*120 if f['seen_valid'] else None},'candidates':[
 {'id':'retake','title':'协同推进回防','conditions':['确认可走路线与清点、拆包所需时间','队友可以同步，或存在必须立即行动的理由'],'risks':['逐个进入对手枪线','把直线距离误当真实路线时间'],'response_checks':['敌人主动前压','敌人守包拖延','队友晚到']},
 {'id':'regroup','title':'短暂等待集合','conditions':['等待能改善同步和补枪条件','等待后仍留足清点及拆包时间'],'risks':['错过拆包窗口','队友并非正在支援'],'response_checks':['敌人利用等待调整位置','队友停留或改走另一条路线']},
 {'id':'save','title':'撤离并保留装备','conditions':['回防机会和资源损失经人工或可信环境评估后不值得交换','确认撤离路线、爆炸范围与追击风险'],'risks':['过早放弃本可争取的回合','在撤离路上被截杀'],'response_checks':['敌人追枪','撤离路线被切断']}
 ],'recommended_candidate':None,'ready_for_player_advice':False,'limitations':['Candidate conditions are handcrafted prompts for review, not learned counterfactual values.','Limited displacement cannot establish waiting intent; withdrawal cannot establish saving intent.','No navigation graph, dynamic door, active smoke/fire simulation or voice communication reconstruction in this strategy pilot.','Future behaviour predictions must not be read as recommendation probabilities.']}

def inspect_sample(index):
 rows=json.loads((DIRECTORY/'rows.json').read_text());protocol=json.loads((DIRECTORY/'protocol.json').read_text())
 if type(index) is not int or not 0<=index<len(rows):return {'error':'Unknown strategy sample index'}
 row=rows[index];result=candidates(dict(zip(protocol['features'],row['h'][-1])));result.update(sample_index=index,map=row['map'],history_seconds=12,known_positions=row.get('view'))
 review=DIRECTORY/'review/index.json'
 if review.exists():
  entry=next((r for r in json.loads(review.read_text()) if r['sample_index']==index),None)
  if entry:
   detail=json.loads((review.parent/(entry['id']+'.json')).read_text())
   result['team_economy']=detail['economy'];result['current_team']=detail['team']
 if (DIRECTORY/'metrics.json').exists():
  import numpy as np
  metrics=json.loads((DIRECTORY/'metrics.json').read_text());arm=metrics['selected_by_validation'];p=np.load(DIRECTORY/'probabilities.npz')[arm][index];threshold=metrics['abstention']['threshold']
  result['behaviour_prediction']={'model':arm,'probabilities':dict(zip(protocol['labels'],p.tolist())),'abstain':bool(p.max()<threshold),'meaning':'prediction of weak geometric behaviour labels, not tactical quality'}
 return result
