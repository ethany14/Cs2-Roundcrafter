"""Source-grounded tactical constraints. The language layer cannot invent coordinates."""
import math
from .nuke_teaching import plan, ACTIONS

# Reviewed interpretation of source role descriptions, not a general LLM parser.
BINDINGS={
 'heaven_smoke':('Roof','Heaven','Ramp','封 Heaven 枪线，为 A 假打提供掩护'),
 'vent_smoke':('TSpawn','Vents','Lobby','先给管道烟，再转 Lobby / Radio'),
 'outside_smoke':('TSpawn','Outside','Roof','携包者给外场过点烟，然后上屋顶'),
}

def intent(action_id='heaven_smoke'):
 if action_id not in BINDINGS: raise ValueError('Unsupported smoke action')
 p=plan();a=next(x for x in ACTIONS if x['id']==action_id);r=next(x for x in p['roles'] if x['id']==a['role']);origin,target,next_area,purpose=BINDINGS[action_id]
 return {'schema':1,'tactic_id':p['id'],'map':p['map'],'side':p['side'],'action':a['id'],'role':a['role'],'kind':a['type'],'origin_area':origin,'target_area':target,'next_area':next_area,'purpose':purpose,'release_clock':a['at'],'dependencies':a['before'],'source_url':p['source_url'],'source_steps':r['steps_zh'],'interpretation':'reviewed_source_binding_not_runtime_llm','throw_modes':['stand_left'],'max_bounces':2,'pitch_range':[-75,15],'policy_note':'站立左键、最多两次反弹、角度范围是首版产品限制，不是原战术事实；无解不代表战术不可行。','target_precision':'callout_region_only_not_verified_sightline','timing':{'clock_direction':'countdown','tolerance':2,'tolerance_basis':'prototype_policy','downstream_signal':'NADES','downstream_clock':100,'route_time':None},'unknown':['目标封锁枪线尚未精确标定','出生位到投掷点及后续路线耗时未实测','区域名来自采样地名，不能替代完整导航网格']}

def assess(spec,candidate,context=None):
 context=context or {};blocked=[];unknown=[]
 for k in ('map','side','role','origin_area'):
  if candidate.get(k)!=spec[k]:blocked.append(k+' 不符合战术约束')
 if candidate.get('target_area')!=spec['target_area']:blocked.append('目标区域不符')
 if candidate.get('mode') not in spec['throw_modes']:blocked.append('投掷方式不在首版支持范围')
 pitch=candidate.get('pitch');yaw=candidate.get('yaw');pos=candidate.get('position',[])
 if type(pitch) not in (int,float) or not math.isfinite(pitch) or not spec['pitch_range'][0]<=pitch<=spec['pitch_range'][1]:blocked.append('俯仰角超出搜索范围')
 if type(yaw) not in (int,float) or not math.isfinite(yaw):blocked.append('朝向角无效')
 if not isinstance(pos,list) or len(pos)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos):blocked.append('站位坐标无效')
 if candidate.get('standable') is not True:blocked.append('没有通过落脚和身体空间检查')
 if candidate.get('bounces',99)>spec['max_bounces']:blocked.append('反弹次数过多')
 if candidate.get('reached_target') is not True:blocked.append('未到达目标区域')
 if candidate.get('next_area')!=spec['next_area']:blocked.append('后续去向与角色职责冲突')
 known=context.get('completed',[])
 if not isinstance(known,list) or any(not isinstance(x,str) for x in known):raise ValueError('Invalid completed actions')
 for dep in spec['dependencies']:
  if dep not in known:unknown.append('前置动作未确认：'+dep)
 clock=context.get('clock');eta=context.get('travel_seconds');at=spec['release_clock'];tol=spec['timing']['tolerance']
 for name,v in [('clock',clock),('travel_seconds',eta)]:
  if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0 or (name=='clock' and v>115)):raise ValueError('Invalid '+name)
 if at is not None and clock is not None:
  if clock<at-tol:blocked.append('已错过投掷窗口')
  elif eta is not None and clock-eta<at-tol:blocked.append('给定赶路耗时无法赶上投掷窗口')
  elif eta is None:unknown.append('到投掷点的实际耗时未知')
 else:unknown.append('投掷时机需结合当前回合确认')
 robust=candidate.get('robustness')
 if robust is None:unknown.append('小幅瞄准误差的容错未测试')
 elif robust.get('tested')!=5 or robust.get('passed',0)<4:blocked.append('小幅瞄准扰动下不稳定：至少需要 4/5 通过粗区域测试')
 if candidate.get('exposure_checked') is not True:unknown.append('敌方可能枪线下的暴露风险未验证')
 corridor=candidate.get('target_corridor')
 if corridor is None or not corridor.get('tested'):unknown.append('尚未检查目标枪线')
 elif not corridor.get('passed'):blocked.append('粗烟雾包络无法覆盖全部代表性目标枪线')
 if candidate.get('coverage_verified') is not True:unknown.append('烟雾封锁效果未验证')
 if candidate.get('game_validated') is not True:unknown.append('投掷物理与玩家操作尚未游戏内验证')
 unknown.append('后续转点与连续投掷耗时待验证')
 return {'status':'rejected' if blocked else 'practice_candidate','blocked':blocked,'unknown':unknown,'recommended':False}

def command(c):
 pos=c['position'];ang=[c['pitch'],c['yaw'],0.]
 if any(type(x) not in (int,float) or not math.isfinite(x) for x in pos+ang) or len(pos)!=3:raise ValueError('Invalid command coordinates')
 return 'setpos '+' '.join(f'{x:.6f}' for x in pos)+'; setang '+' '.join(f'{x:.6f}' for x in ang)


def latest():
 import json
 from .casebook import ROOT
 p=ROOT/'outputs/tactics/tactical-solver.json'
 return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'status':'not_run','intent':intent(),'candidates':[]}

def check_latest(raw):
 if not isinstance(raw,dict) or set(raw)-{'clock','travel_seconds','candidate_index'}:raise ValueError('Invalid fields')
 data=latest();i=raw.get('candidate_index',0)
 pool=data.get('candidates') or data.get('diagnostics',[])
 if type(i) is not int or not 0<=i<len(pool):raise ValueError('No such candidate')
 return assess(data['intent'],pool[i],{k:v for k,v in raw.items() if k!='candidate_index'})
