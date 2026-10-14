"""Bounded free-position experiments using the existing collision/throw model."""
import copy
import hashlib
import json
import math
import threading
import time
import uuid
from functools import lru_cache
import numpy as np
from .casebook import ROOT
from .geometry import Mesh
from .grenade_search import simulate, standable, PARAMS, jump_release, JUMP_PROFILE
from .tactical_solver import command
from .throw_movement import LABELS,movement_release,execution_steps
from .lineup_catalog import write_json

MAPS = ('de_nuke','de_mirage','de_inferno','de_dust2','de_ancient','de_anubis','de_cache')
RUNS = ROOT/'outputs/free-lab'
LOCK = threading.RLock()
RUN_LOCK = threading.Lock()
JOBS = {}

def available():
    return [m for m in MAPS if (ROOT/'data/maps/all'/m/'scene.npz').exists()]

@lru_cache(maxsize=1)
def scene(name):
    if name not in available(): raise ValueError('地图碰撞数据尚未准备')
    path=ROOT/'data/maps/all'/name/'scene.npz'
    meta=json.loads(path.with_suffix('.json').read_text())
    allowed=[i for i,g in enumerate(meta['groups']) if g.get('SurfaceProperty')!='audioblocker']
    with np.load(path) as d: mesh=Mesh(d['triangles'][np.isin(d['groups'],allowed)].reshape(-1,3,3))
    mesh.sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    return mesh

@lru_cache(maxsize=2)
def geometry(name):
    if name not in available():raise ValueError('Unsupported map')
    path=ROOT/'data/maps/all'/name/'scene.npz'
    meta=json.loads(path.with_suffix('.json').read_text())
    allowed=[i for i,g in enumerate(meta['groups']) if g.get('SurfaceProperty')!='audioblocker']
    with np.load(path) as d:return d['triangles'][np.isin(d['groups'],allowed)].astype('<f4').tobytes()

def validate(raw):
    if not isinstance(raw,dict) or set(raw)-{'map','origin','target','radius','max_simulations','seconds','mode','run_distance'}: raise ValueError('实验参数无效')
    if raw.get('map') not in available(): raise ValueError('地图尚不支持')
    for key in ('origin','target'):
        p=raw.get(key)
        if not isinstance(p,list) or len(p)!=3 or any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>30000 for v in p): raise ValueError('需要有效的站位和落点坐标')
    if raw.get('mode','auto') not in ('auto','auto_all',*LABELS): raise ValueError('不支持的投掷方式')
    out={**raw,'mode':raw.get('mode','auto')}
    for k,default,lo,hi in [('radius',64,8,160),('max_simulations',180,10,400),('seconds',45,2,90),('run_distance',128,32,256)]:
        v=raw.get(k,default)
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi: raise ValueError('实验预算或容差超出范围')
        out[k]=v
    out['max_simulations']=int(out['max_simulations'])
    return out

def surfaces(raw):
    if not isinstance(raw,dict) or set(raw)-{'map','x','y','ceiling','floor'} or raw.get('map') not in available():raise ValueError('Invalid surface request')
    for k in ('x','y','ceiling','floor'):
        if type(raw.get(k)) not in (int,float) or not math.isfinite(raw[k]) or abs(raw[k])>30000:raise ValueError('Invalid surface coordinates')
    m=scene(raw['map']);x,y=raw['x'],raw['y'];top=raw['ceiling'];bottom=raw['floor'];rows=[]
    if top<=bottom:raise ValueError('Invalid height interval')
    for hit in m.intersections([x,y,top+1],[x,y,bottom-1],limit=60):
        tri=m.tri[hit['triangle']];normal=np.cross(tri[1]-tri[0],tri[2]-tri[0])
        if normal[2]<.7*np.linalg.norm(normal):continue
        z=top+1+(bottom-top-2)*hit['fraction']+.5
        if any(abs(z-r['position'][2])<3 for r in rows):continue
        p=[x,y,z];rows.append({'position':p,'standable':standable(m,p)})
        if len(rows)>=8:break
    return {'surfaces':rows,'scope':'upward static collision surfaces; sparse footing check only'}

def _solve_mode(request,cancelled=None,progress=lambda x:None,mesh=None):
    r=request; cancel=cancelled or threading.Event();started=time.monotonic()
    m=mesh if mesh is not None else scene(r['map'])
    result={'request':r,'status':'running','candidates':[],'nearest':None,'simulations':0,
            'map_sha256':getattr(m,'sha256',None),'physics':PARAMS,'game_validated':False,
            'limits':['左键烟：站立、原地跳、W 点按跳、蹲稳跳、平地助跑跳；动态门和玻璃变化未求解',
                      '静态碰撞几何，无游戏贴图；落脚为稀疏探针检查',
                      '飞行、反弹与停稳模型未完成游戏校准；命中容差不代表封烟效果',
                      '有限角度搜索失败不证明不存在投法；没有外部模型或网络调用']}
    def stop():
        if cancel.is_set(): return 'cancelled'
        if time.monotonic()-started>=r['seconds'] or result['simulations']>=r['max_simulations']: return 'budget_exhausted'
    if stop():result['status']=stop();return result
    if not standable(m,r['origin']):
        result.update(status='invalid_origin',reason='站位未通过落脚/身体空间检查；请选择地面并避开墙边。');return result
    if r['mode']=='jump_left' and jump_release(m,r['origin']) is None:
        result.update(status='jump_blocked',reason='头顶空间不足，原地跳投未通过起跳空间检查。');return result
    class Stopped(Exception):pass
    def checkpoint():
        if cancel.is_set() or time.monotonic()-started>=r['seconds']:raise Stopped()
    launch_cache={}
    p=np.asarray(r['origin']);target=np.asarray(r['target']);yaw=math.degrees(math.atan2(target[1]-p[1],target[0]-p[0]));tested=set();best=[];evaluations={}
    def trial(pitch,angle):
        if stop():return
        key=(round(pitch,4),round(angle,4))
        if key in tested:return evaluations.get(key)
        if not -85<=pitch<=85:return
        tested.add(key);result['simulations']+=1
        try:
            launch=None
            if r['mode'] in ('w_jump_left','crouch_jump_left','run_jump_left'):
                cache_key=round(angle,4)
                if cache_key not in launch_cache:launch_cache[cache_key]=movement_release(m,p,angle,r['mode'],r['run_distance'],checkpoint)
                launch=launch_cache[cache_key]
                if launch is None:return
            sim=simulate(m,p.tolist(),pitch,angle,checkpoint=checkpoint,mode=r['mode'],launch_override=launch)
        except Stopped:return
        if sim:
            distance=float(np.linalg.norm(np.asarray(sim['end'])-target))
            c={'position':p.tolist(),'pitch':pitch,'yaw':angle,'distance':distance,'end':sim['end'],
               'trajectory':sim['path'],'flight_seconds':sim['flight_seconds'],'bounces':sim['bounces'],
               'game_validated':False,'mode':r['mode']}
            if launch is not None:c['launch_assumptions']=launch
            evaluations[key]=c
            best.append(c);best.sort(key=lambda x:x['distance']);del best[8:]
            result['nearest']={k:v for k,v in best[0].items() if k!='trajectory'}
        if result['simulations']%5==0:progress({'simulations':result['simulations'],'nearest':result['nearest']})
        return evaluations.get(key)
    # Seed both direct ballistic arcs, then use symmetric coarse coverage.
    delta=target-(p+[0,0,PARAMS['eye_height']]);horizontal=float(np.linalg.norm(delta[:2]));g=PARAMS['gravity'];speed=PARAMS['speed']
    disc=speed**4-g*(g*horizontal**2+2*delta[2]*speed**2)
    if horizontal>1 and disc>=0:
        for sign in [-1,1]:
            elevation=math.degrees(math.atan((speed**2+sign*math.sqrt(disc))/(g*horizontal)))
            effective=-elevation
            pitch=(effective+10)*(.9 if effective<-10 else 1.125)
            for dp in [0,-3,3]:trial(pitch+dp,yaw)
    # Full downward range is essential for short throws; old code stopped at +25.
    for dy in [0,-12,12,-30,30]:
        for pitch in [-40,-20,0,20,40,60,80,-60,-80]:
            trial(pitch,yaw+dy)
            if stop():break
        if stop():break
    # Refine several basins repeatedly; consume the available budget instead of
    # always stopping after the old fixed 114 evaluations.
    seeds=list(best[:5])
    for seed in seeds:
        center=seed
        for step in [6,3,1,.3]:
            for iteration in range(3):
                before=center['distance'];neighbors=[center]
                for dp,dy in [(-step,0),(step,0),(0,-step),(0,step)]:
                    candidate=trial(center['pitch']+dp,center['yaw']+dy)
                    if candidate:neighbors.append(candidate)
                    if stop():break
                center=min(neighbors,key=lambda c:c['distance'])
                if stop() or center['distance']>=before:break
            if stop():break
        if stop():break
    if not stop() and (not best or best[0]['distance']>r['radius']):
        # Wider side/back banks, symmetrically rather than the old one-sided cutoff.
        for dy in [-60,60,-100,100,180]:
            for pitch in [-60,-40,-20,0,30,60]:
                trial(pitch,yaw+dy)
                if stop():break
            if stop():break
    free_range=speed/g*math.sqrt(max(0,speed**2-2*g*delta[2]))
    result['diagnostics']={'horizontal_distance':round(horizontal,1),'height_difference':round(float(delta[2]),1),
        'standing_reference_range':round(free_range,1),'ideal_unobstructed_range':round(free_range,1),'direct_arc_exists':bool(disc>=0),
        'scope':'ideal ballistic diagnostic only; collisions can alter range; not proof of impossibility'}
    for c in best:
        if c['distance']>r['radius']:continue
        if any(abs(c['pitch']-x['pitch'])<.5 and abs(c['yaw']-x['yaw'])<.5 for x in result['candidates']):continue
        # Aim ray uses player view angles, not the corrected release direction.
        c['aim_eye_height']=46. if r['mode']=='crouch_jump_left' else 64.
        eye=p+[0,0,c['aim_eye_height']];a,b=map(math.radians,[c['pitch'],c['yaw']]);direction=np.array([math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),-math.sin(a)])
        hits=m.intersections(eye,eye+direction*8000,limit=1)
        c['aim_point']=(eye+direction*8000*hits[0]['fraction']).tolist() if hits else None
        c['aim_direction_point']=(eye+direction*1000).tolist()
        c['aim_kind']='surface_intersection' if hits else 'sky_direction_only'
        c['practice_command']=command(c)
        c['execution_steps']=execution_steps(c)
        if r['mode']=='jump_left':c['launch_assumptions']=jump_release(m,p)
        result['candidates'].append(c)
        if len(result['candidates'])==3:break
    result.update(status='cancelled' if cancel.is_set() else 'experimental_candidates' if result['candidates'] else stop() or 'no_solution_in_bounded_search',
                  stop_reason=stop(),elapsed_seconds=round(time.monotonic()-started,2))
    if not result['candidates'] and not cancel.is_set():
        result['reason']=('目标超出站立投掷的理想直达参考范围；可尝试自动选择投掷方式或调整站位。' if disc<0 else
                          '当前角度与时限内未找到落入容差的停稳轨迹。可能受墙体、屋顶或反弹影响；可核对目标高度或调整站位。')
        if best:result['diagnostic_trajectory']=best[0]['trajectory']
    if cancel.is_set():result['candidates']=[]
    return result

def solve(request,cancelled=None,progress=lambda x:None,mesh=None):
    r=validate(request);event=cancelled or threading.Event();started=time.monotonic()
    m=mesh if mesh is not None else scene(r['map'])
    modes=list(LABELS) if r['mode']=='auto_all' else ['stand_left','jump_left'] if r['mode']=='auto' else [r['mode']]
    results=[];used=0
    for mode in modes:
        remaining=r['seconds']-(time.monotonic()-started)
        if event.is_set() or remaining<=0 or used>=r['max_simulations']:break
        # Reserve a share of both budgets so standing failure cannot starve jumping.
        remaining_modes=len(modes)-len(results)
        seconds=remaining/remaining_modes
        count=max(1,(r['max_simulations']-used)//remaining_modes)
        def update(d):progress({**d,'simulations':used+d.get('simulations',0),'searching_mode':mode})
        result=_solve_mode({**r,'mode':mode,'seconds':seconds,'max_simulations':count},event,update,m)
        results.append(result);used+=result['simulations']
        if (result['candidates'] and r['mode']!='auto_all') or result['status'] in ('invalid_origin','cancelled'):break
    if not results:
        return {'request':r,'status':'cancelled' if event.is_set() else 'budget_exhausted','simulations':0,'candidates':[],
                'mode_decision':{'code':'unknown','message':'计算已取消或预算耗尽，尚不能判断是否需要跳投。'}}
    chosen=next((x for x in results if x['candidates']),results[-1])
    out={**chosen,'request':r,'simulations':used,'elapsed_seconds':round(time.monotonic()-started,2)}
    out['mode_checks']=[{'mode':x['request']['mode'],'label':LABELS[x['request']['mode']],'status':x['status'],'simulations':x['simulations'],
                        'nearest_distance':(x.get('nearest') or {}).get('distance')} for x in results]
    if chosen['candidates'] and not event.is_set():
        mode=chosen['candidates'][0]['mode']
        code='standing_sufficient' if mode=='stand_left' else 'jump_recommended'
        message='已找到站立投掷候选，无需跳投（模型结论）。' if mode=='stand_left' else (f'建议{LABELS[mode]}；此前方式有限搜索未命中，不证明必须使用此方式。' if r['mode'] in ('auto','auto_all') else f'找到{LABELS[mode]}实验候选；未比较其他方式。')
    else:
        code='unknown';message='尚不能判断是否需要跳投：未找到合格候选或计算未完成。'
        if event.is_set():out.update(status='cancelled',candidates=[])
    out['mode_decision']={'code':code,'message':message,'game_validated':False}
    if r['mode']=='auto_all':
        difficulty={'stand_left':(1,'简单'),'jump_left':(2,'较简单'),'crouch_jump_left':(3,'中等'),
                    'w_jump_left':(4,'较难'),'run_jump_left':(5,'困难')}
        candidates=[]
        for stage in results:
            for candidate in stage['candidates']:
                rank,label=difficulty[candidate['mode']]
                candidates.append({**candidate,'difficulty_rank':rank,'difficulty_label':label,
                    'difficulty_basis':'product_rule_input_coordination_and_movement_not_measured_success_rate'})
        candidates.sort(key=lambda c:(c['difficulty_rank'],c['distance']))
        if event.is_set():candidates=[]
        out['candidates']=candidates
        for check,stage in zip(out['mode_checks'],results):
            check['candidate_count']=len(stage['candidates']) if not event.is_set() else 0
            check['stop_reason']=stage.get('stop_reason')
        for mode in modes[len(results):]:
            out['mode_checks'].append({'mode':mode,'label':LABELS[mode],'status':'not_started',
              'simulations':0,'candidate_count':0,'nearest_distance':None,
              'reason':'cancelled' if event.is_set() else 'invalid_origin' if chosen['status']=='invalid_origin' else 'budget_exhausted'})
        searched=len(results)
        out['comparison']={'attempted':searched,'total':len(modes),'all_attempted':searched==len(modes),
                          'sort_default':'difficulty_then_error','exhaustive':False}
        nearest=min((stage['nearest'] for stage in results if stage.get('nearest')),key=lambda c:c['distance'],default=None)
        out['nearest']=nearest
        out['stop_reason']='cancelled' if event.is_set() else 'budget_exhausted' if searched<len(modes) and chosen['status']!='invalid_origin' else None
        if candidates:
            out['status']='experimental_candidates'
            out['mode_decision']={'code':'choose_candidate','message':f'已尝试 {searched}/{len(modes)} 种方式，找到 {len(candidates)} 个实验候选，请按难度或误差自行选择。','game_validated':False}
        elif event.is_set():out.update(status='cancelled')
    out['jump_profile']=JUMP_PROFILE
    return out


def start(raw):
    request=validate(raw)
    if not RUN_LOCK.acquire(False):raise RuntimeError('已有实验在计算，请等待或取消')
    identifier=uuid.uuid4().hex;event=threading.Event()
    state={'id':identifier,'status':'running','request':request,'simulations':0,'candidates':[]}
    with LOCK:JOBS[identifier]=(state,event)
    def update(delta):
        with LOCK:state.update(delta)
    def worker():
        try:update(solve(request,event,update))
        except Exception:update({'status':'failed','reason':'计算失败；检查碰撞地图与参数。'})
        finally:
            try:
                with LOCK:write_json(RUNS/(identifier+'.json'),state)
            finally:RUN_LOCK.release()
    threading.Thread(target=worker,daemon=True,name='free-lab').start()
    return {'id':identifier,'status':'running'}

def get(identifier):
    import re
    if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('实验不存在')
    with LOCK:
        if identifier in JOBS:return copy.deepcopy(JOBS[identifier][0])
    path=RUNS/(identifier+'.json')
    if not path.exists():raise ValueError('实验不存在')
    return json.loads(path.read_text(encoding='utf-8'))

def cancel(identifier):
    get(identifier)
    with LOCK:
        if identifier in JOBS:JOBS[identifier][1].set()
    return {'id':identifier,'status':'cancelling'}
