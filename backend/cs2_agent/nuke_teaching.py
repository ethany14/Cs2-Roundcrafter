"""Nuke pilot: deterministic execution constraints and locally observed teaching."""
import itertools,json,math
from .casebook import ROOT
PILOT=ROOT/'data/knowledge/metastack/pilot.json'
DATA=ROOT/'data/knowledge/metastack/teaching.json'
ROLES=['floater','roof_support','lobby','outside','bomb']
# Each occurrence is an action, even when the source nade ID repeats.
ACTIONS=[
 dict(id='outside_smoke',role='bomb',type='smoke',nade='1361',before=[],at=None),
 dict(id='vent_smoke',role='lobby',type='smoke',nade='1362',before=[],at=None),
 dict(id='heaven_smoke',role='roof_support',type='smoke',nade='6518',before=[],at=106),
 dict(id='hut_fire',role='bomb',type='fire',nade='1370',before=['outside_smoke'],at=106),
 dict(id='nades',role='floater',type=None,before=['heaven_smoke','hut_fire','vent_smoke'],at=100),
 dict(id='door_he',role='floater',type='he',before=['nades'],at=None),
 dict(id='vent_bounce_smoke',role='floater',type='smoke',before=['door_he'],at=None),
 dict(id='vent_fire',role='floater',type='fire',before=['vent_bounce_smoke'],at=None),
 dict(id='vent_flash',role='floater',type='flash',before=['vent_fire'],at=None),
 dict(id='a_flash_1',role='roof_support',type='flash',nade='1724',before=['nades'],at=None),
 dict(id='backsite_fire',role='roof_support',type='fire',nade='1369',before=['a_flash_1'],at=None),
 dict(id='a_flash_2',role='roof_support',type='flash',nade='1724',before=['backsite_fire'],at=None),
 dict(id='go',role='lobby',type=None,before=['vent_flash','a_flash_2'],at=None),
 dict(id='entry_1',role='lobby',type=None,before=['go'],at=None),
 dict(id='entry_2',role='outside',type=None,before=['entry_1'],at=None),
 dict(id='entry_3',role='bomb',type=None,before=['entry_2'],at=None),
 dict(id='entry_4',role='roof_support',type=None,before=['entry_3'],at=None),
 dict(id='plant',role='bomb',type=None,before=['entry_3'],at=None),
]
UTILITY={'smoke','flash','fire','he','decoy'}
def plan():
 c=next(x for x in json.loads(PILOT.read_text(encoding='utf-8'))['tactics'] if x['id']=='metastack-64994')
 return {**c,'actions':ACTIONS,'sequence_note':'GO 等待本轮假打道具完成是本原型的保守执行约束；不是从来源推得的精确秒数。','weapons_required':None}
def check(raw):
 if not isinstance(raw,dict) or set(raw)-{'players','clock','completed','map','side','phase','assignment'}:raise ValueError('Invalid fields')
 ps=raw.get('players');clock=raw.get('clock');done=raw.get('completed',[])
 if not isinstance(ps,list) or not 1<=len(ps)<=5 or type(clock) not in (float,int) or not math.isfinite(clock) or not 0<=clock<=115:raise ValueError('Invalid players/clock')
 ids=set()
 for p in ps:
  if not isinstance(p,dict) or set(p)-{'id','alive','cooperates','position_ready','utility','has_c4'}:raise ValueError('Invalid player fields')
  if not isinstance(p.get('id'),str) or not 1<=len(p['id'])<=30 or p['id'] in ids:raise ValueError('Invalid player id')
  ids.add(p['id'])
  for k in ['alive','cooperates','position_ready','has_c4']:
   if p.get(k) is not None and type(p[k]) is not bool:raise ValueError('Invalid flag')
  inv=p.get('utility')
  if inv is not None:
   if not isinstance(inv,dict) or set(inv)-UTILITY or any(type(v) is not int or not 0<=v<=(2 if k=='flash' else 1) for k,v in inv.items()) or sum(inv.values())>4:raise ValueError('Invalid grenade inventory')
 if not isinstance(done,list) or len(done)>len(ACTIONS):raise ValueError('Invalid completed events')
 fixed=raw.get('assignment')
 if fixed is not None and (not isinstance(fixed,dict) or set(fixed)!=set(ROLES) or len(set(fixed.values()))!=5 or any(v not in ids for v in fixed.values())):raise ValueError('Invalid fixed assignment')
 if done and fixed is None:raise ValueError('Progress requires a fixed role assignment')
 times={};actions={a['id']:a for a in ACTIONS}
 for e in done:
  if not isinstance(e,dict) or set(e)!={'id','clock'} or e['id'] not in actions or e['id'] in times or type(e['clock']) not in (int,float) or not math.isfinite(e['clock']) or not clock<=e['clock']<=115:raise ValueError('Invalid event time')
  times[e['id']]=e['clock']
 blocked=[];unknown=[];warnings=[]
 for k,v in [('map','de_nuke'),('side','T'),('phase','opening')]:
  if raw.get(k)!=v:blocked.append(k+'：仅支持 Nuke T 方开局')
 for a in ACTIONS:
  if a['id'] in times:
   if any(dep not in times or times[dep]<times[a['id']] for dep in a['before']):blocked.append(a['id']+'：前置动作未完成或顺序错误')
   if a['at'] is not None and abs(times[a['id']]-a['at'])>2:warnings.append(a['id']+'：偏离来源时机超过 2 秒，需重评')
  elif a['at'] is not None and clock<a['at']-2:blocked.append(a['id']+'：已错过原版时间窗口')
 needs={r:{} for r in ROLES}
 for a in ACTIONS:
  if a['id'] not in times and a['type']:needs[a['role']][a['type']]=needs[a['role']].get(a['type'],0)+1
 living=[p for p in ps if p.get('alive') is True]
 if len(living)<5:blocked.append('完整战术需要 5 名已确认存活的玩家')
 def fit(role,p):
  b=[];u=[]
  if p.get('cooperates') is False:b.append('无法参与口令配合')
  elif p.get('cooperates') is None:u.append('配合意愿未知')
  if p.get('position_ready') is not True or fixed is None:u.append('分配后的站位/赶路时间未确认')
  if role=='bomb' and 'plant' not in times:
   if p.get('has_c4') is False:b.append('没有 C4')
   elif p.get('has_c4') is None:u.append('C4 归属未知')
  for k,n in needs[role].items():
   value=(p.get('utility') or {}).get(k)
   if value is None:u.append(k+' 数量未知')
   elif value<n:b.append(f'{k} 需要 {n}，现有 {value}')
  return b,u
 assignments=[]
 for perm in itertools.permutations(living,5):
  if fixed and any(fixed[r]!=p['id'] for r,p in zip(ROLES,perm)):continue
  rows=[dict(role=r,player=p['id'],blocked=fit(r,p)[0],unknown=fit(r,p)[1],remaining_utility=needs[r]) for r,p in zip(ROLES,perm)]
  assignments.append((sum(len(x['blocked']) for x in rows),sum(len(x['unknown']) for x in rows),rows))
 best=min(assignments,key=lambda x:x[:2]) if assignments else None
 if best:
  for x in best[2]:
   blocked.extend(x['player']+' / '+x['role']+'：'+b for b in x['blocked']);unknown.extend(x['player']+' / '+x['role']+'：'+u for u in x['unknown'])
 unknown+=['精确行走耗时、出生位与投掷成功率尚未实测','枪械护甲预算未被来源明确约束，当前不评估购买方案']
 return {'status':'blocked' if blocked else 'conditions_passed_with_unknowns','blocked':blocked,'unknown':unknown,'warnings':warnings,'assignment':best[2] if best else [],'next_actions':[a['id'] for a in ACTIONS if a['id'] not in times and all(dep in times for dep in a['before'])], 'ready_for_recommendation':False,'timing_tolerance_seconds':2,'timing_note':'2 秒是原型容差，不是经过职业数据验证的阈值；完成记录视为玩家确认，本端点不自动读取 demo。'}
def teaching():return json.loads(DATA.read_text(encoding='utf-8'))
