"""Local 3D decision studio. Prospective evidence and actual future are separate."""
import argparse
import base64
import hashlib
import json
import math
import subprocess
from pathlib import Path
import numpy as np
from .casebook import ROOT,connect,get_case,retrieve,shortlist
from .map_assets import load_scene
from .smoke_voxels import frames_for_case,decode

DIRECTORY=ROOT/'data/studio'


def visible_players(players,side,actor):
    friends={p['player'] for p in players if p['side']==side and p['alive']}
    result=[]
    for p in players:
        if p['side']!=side and not friends.intersection(p.get('approximate_spotted_by') or []):continue
        result.append({k:p[k] for k in ('player','side','alive','position','yaw','pitch','duck_amount') if k in p} |
                      {'role':'self' if p['player']==actor else ('ally' if p['side']==side else 'enemy'),
                       'information_source':'self_or_teammate' if p['side']==side else 'approximate_team_spotting'})
    return result


def segment_safe(mesh,a,b):
    # Coarse swept-body samples, not a navmesh/physics solver. Reject unsupported climbs.
    if abs(b[2]-a[2])>18:return False
    d=np.asarray(b)-a
    if np.linalg.norm(d)<1e-5:return True
    for offset in ([0,0,8],[0,0,36],[0,0,62],[14,0,36],[-14,0,36],[0,14,36],[0,-14,36]):
        if mesh.blocked(np.asarray(a)+offset,np.asarray(b)+offset):return False
    # Require floor support along the route; sparse check remains only a coarse gate.
    for t in np.linspace(0,1,max(2,math.ceil(np.linalg.norm(d)/20))):
        p=np.asarray(a)+d*t
        if not mesh.blocked(p+[0,0,10],p-[0,0,24]):return False
    return True


def routes_for(case,mesh):
    actor=next(p for p in case['evidence']['snapshot'] if p['player']==case['actor']);origin=actor['position']
    routes=[{'id':'hold','title':'稳住角度','path':[origin,origin],'yaw':actor['yaw'],'duration':6.,'check':'stationary',
             'purpose':'保持当前掩体和观察方向，等队友形成配合。','tradeoff':'等待可能丢失时间与主动权。'}]
    history=[]
    for frame in reversed(case['evidence']['history']):
        p=next((p for p in frame['players'] if p['player']==case['actor']),None)
        if p and (not history or np.linalg.norm(np.asarray(p['position'])-history[-1])>4):history.append(p['position'])
    if len(history)>1:
        path=[origin]
        for point in history[1:]:
            if not segment_safe(mesh,path[-1],point):break
            path.append(point)
        if len(path)>1 and np.linalg.norm(np.asarray(path[-1])-origin)>15:
            routes.append({'id':'retreat','title':'回收站位','path':path,'yaw':actor['yaw'],'duration':6.,'check':'coarse_body_and_floor_checked',
                           'purpose':'沿自己刚才经过的路线退回，争取重新组织。','tradeoff':'可能让出控制区域；对手反应仍不确定。'})
    yaw=math.radians(actor['yaw'])
    for sign in (1,-1):
        endpoint=(np.asarray(origin)+np.array([-math.sin(yaw),math.cos(yaw),0])*sign*64).tolist()
        if segment_safe(mesh,origin,endpoint):
            routes.append({'id':'sidestep' if sign==1 else 'sidestep_back','title':'调整观察位置','path':[origin,endpoint],
                           'yaw':actor['yaw'],'duration':3.,'check':'coarse_body_and_floor_checked',
                           'purpose':'小幅换位，改变观察角度，再重新确认信息。','tradeoff':'换位可能暴露身体，尚未验证敌方视线。'})
            break
    if len(routes)<3:
        routes.append({'id':'scan','title':'停步检查另一方向','path':[origin,origin],'yaw':actor['yaw']+50,'duration':3.,'check':'stationary',
                       'purpose':'停止前移，检查相邻方向后再决定。','tradeoff':'转移注意力可能漏掉原来的架枪方向。'})
    if case['features']['own_alive']==1:
        routes[0]['purpose']='原地观察短时信息变化；是否等待取决于安包时间和装备，不能等待不存在的队友。'
    for degrees in range(0,360,45):
        radians=math.radians(degrees)
        for distance in (320,200,120):
            end=(np.asarray(origin)+np.array([math.cos(radians),math.sin(radians),0])*distance).tolist()
            if any(np.linalg.norm(np.asarray(end)-r['path'][-1])<80 for r in routes):continue
            if segment_safe(mesh,origin,end):
                routes.append({'id':f'move_{degrees}_{distance}','title':f'候选通路 {degrees}°',
                    'path':[origin,end],'yaw':degrees,'duration':max(1.5,distance/100),'check':'coarse_body_and_floor_checked',
                    'purpose':f'地图允许沿 {degrees}° 方向移动 {distance} 单位，需由 Agent 结合目标判断用途。',
                    'tradeoff':'尚未证明目标方向和暴露风险合适。'})
                break
    for route in routes:
        end=np.asarray(route['path'][-1])+[0,0,64]
        route['nearby_cover_rays']=sum(mesh.blocked(end,end+np.array([math.cos(a),math.sin(a),0])*240) for a in np.arange(0,2*math.pi,math.pi/4))
        route['length_units']=round(sum(np.linalg.norm(np.asarray(b)-a) for a,b in zip(route['path'],route['path'][1:])),1)
    return routes


def baseline_plans(routes):
    return [{'id':r['id'],'route_id':r['id'],'title':r['title'],'reason':r['purpose'],'risks':[r['tradeoff']],
             'assumptions':['地图检查只是粗筛，尚无完整移动物理。','其他玩家的响应是分支假设，不是已知结果。'],
             'response_notes':{'continue':'其他人延续最近可观察的移动。','cooperate':'队友在可行时向你的选择靠拢。','counter':'已发现的敌人尝试换位反制；未知敌人仅标记风险区域。'}} for r in routes]


def response_catalog(case,mesh,players,routes):
    catalog={}
    history=case['evidence']['history']
    for player in players:
        if player['role']=='self' or not player['alive']:continue
        start=player['position'];choices=[{'id':'hold','path':[start,start],'yaw':player['yaw'],'duration':6.,'check':'stationary'}]
        old=next((p for f in reversed(history[:-1]) for p in f['players'] if p['player']==player['player']),None)
        # Hidden enemy history cannot be used even if retained locally in spectator data.
        if old and player['role']=='ally':
            delta=np.asarray(start)-old['position'];length=np.linalg.norm(delta)
            if length>1:
                end=(np.asarray(start)+delta/min(1e9,max(length,1))*min(160,length*4)).tolist()
                if segment_safe(mesh,start,end):choices.append({'id':'continue','path':[start,end],'yaw':player['yaw'],'duration':6.,'check':'coarse_body_and_floor_checked'})
        for route in routes:
            goal=np.asarray(route['path'][-1]);delta=goal-start;distance=np.linalg.norm(delta)
            if player['role']=='ally' and distance>100:
                end=(np.asarray(start)+delta/distance*min(100,distance-80)).tolist()
                if segment_safe(mesh,start,end):choices.append({'id':'support_'+route['id'],'path':[start,end],'yaw':math.degrees(math.atan2(delta[1],delta[0])),'duration':6.,'check':'coarse_body_and_floor_checked'})
        if player['role']=='enemy':
            yaw=math.radians(player['yaw']);end=(np.asarray(start)+np.array([-math.sin(yaw),math.cos(yaw),0])*48).tolist()
            if segment_safe(mesh,start,end):choices.append({'id':'counter','path':[start,end],'yaw':player['yaw'],'duration':4.,'check':'coarse_body_and_floor_checked'})
        catalog[player['player']]=choices
    return catalog


def build():
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    mesh=load_scene()
    # Indexed, simplified collision rendering; game units -> metres-like display coordinates.
    vertices,inverse=np.unique(mesh.tri.astype('<f4').reshape(-1,3),axis=0,return_inverse=True)
    points=vertices[:,[0,2,1]]/100.;points[:,2]*=-1
    binary=np.array([len(points),len(inverse)],dtype='<u4').tobytes()+points.astype('<f4').tobytes()+inverse.astype('<u4').tobytes()
    (DIRECTORY/'map.bin').write_bytes(binary)
    groups=[]
    for i,material in enumerate(mesh.surfaces):
        indices=np.flatnonzero(mesh.surface_ids==i)
        if len(indices):groups.append({'start':int(indices[0]*3),'count':int(len(indices)*3),'material':material.get('SurfaceProperty','default')})
    (DIRECTORY/'map.json').write_text(json.dumps({'groups':groups,'triangles':len(mesh.tri),'sha256':hashlib.sha256(binary).hexdigest(),'type':'collision_geometry_simplified_visualization'}))
    with connect() as db:
        candidates=shortlist(db,'2398755',40);selected=[];rounds=set()
        for c in candidates:
            if c['round'] in rounds:continue
            selected.append(get_case(db,c['id']));rounds.add(c['round'])
            if len(selected)==6:break
        utility=get_case(db,'49fabf21b1c26f10-3233-008503562d79')
        if not any(c['id']==utility['id'] for c in selected):selected.append(utility)
        if (DIRECTORY/'clutches.json').exists():selected=json.loads((DIRECTORY/'clutches.json').read_text())+selected
        (DIRECTORY/'selected.json').write_text(json.dumps(selected))
        subprocess.run(['node',str(ROOT/'experiments/studio_frames.cjs'),str(ROOT/'data/demos/mouz-vs-spirit-m1-dust2.dem'),str(DIRECTORY/'selected.json'),str(DIRECTORY/'actual-private.json')],check=True,cwd=ROOT)
        actual=json.loads((DIRECTORY/'actual-private.json').read_text());index=[]
        for c in selected:
            players=visible_players(c['evidence']['snapshot'],c['side'],c['actor']);routes=routes_for(c,mesh)
            if 'clutch-' in c['id']:
                db.execute('SAVEPOINT studio_query')
                try:
                    db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?,?)',(c['id'],c['match_id'],c['demo_sha256'],'test',c['map'],c['side'],json.dumps(c)))
                    references=retrieve(db,c['id'])['matches'][:3]
                finally:
                    db.execute('ROLLBACK TO studio_query');db.execute('RELEASE studio_query')
            else:references=retrieve(db,c['id'])['matches'][:3]
            own=next(p for p in c['evidence']['snapshot'] if p['player']==c['actor'])
            # Planning packet has no death tick, future playback, unseen enemy positions or enemy gear.
            knowledge={'case_id':c['id'],'map':c['map'],'round':c['round'],'tick':c['tick'],'side':c['side'],'actor':c['actor'],
                       'alive':{'own':c['features']['own_alive'],'enemy':c['features']['enemy_alive']},'elapsed':c['features']['elapsed'],'bomb_planted':c['features']['bomb_planted'],
                       'players':players,'routes':routes,'own_loadout':{k:own.get(k) for k in ('hp','armor','has_defuser','inventory','weapon')},'bomb_age':c['features'].get('bomb_age'),'planning_horizon':6,'playback_duration':c.get('duration',6),
                       'objective':'残局：独自存活，不能再等待队友配合；CT 需结合安包和剩余时间评估回防或保枪。' if c['features']['own_alive']==1 else '多人局势：先确认可用支援，不假定队友自动补枪。',
                       'reference_cases':[{'id':r['id'],'match_id':r['match_id'],'round':r['round'],'source':r['source_url'],'limits':'structural reference, not an optimal action label'} for r in references],
                       'unknowns':['敌方未发现位置','队伍语音与战术意图','对手反应','精确烟雾透明度','完整导航与移动物理']}
            clouds=[]
            for smoke in frames_for_case(c):
                frame=smoke.get('voxel_frame')
                if not frame or smoke.get('expired_tick') is not None:continue
                try:
                    cells,meta=decode(base64.b64decode(frame['data_base64']));points=((cells-16)*12+frame['position']).tolist()
                    clouds.append({'position':frame['position'],'voxels':points[::max(1,len(points)//1800)],'phase':meta['phase_flag']})
                except ValueError:continue
            responses=response_catalog(c,mesh,players,routes)
            knowledge['other_actor_routes']=responses
            # Unknown enemy risk marker anchored to own proposed endpoint, NEVER true enemy coordinates.
            payload={'id':c['id'],'title':f"Dust2 · 第 {c['round']} 回合"+(' · 长残局' if c.get('duration',6)>6 else ''),'source':c['source_url'],'actor':c['actor'],'side':c['side'],
                     'knowledge':knowledge,'initial':players,'routes':routes,'plans':baseline_plans(routes[:2]),'plan_source':'local_candidates',
                     'responses':responses,'smokes':clouds,'duration':c.get('duration',6),
                     'actual':[{'time':f['time'],'players':visible_players(f['players'],c['side'],c['actor'])} for f in actual[c['id']]],
                     'limits':'替代轨迹为假设，没有预测击杀结果；烟雾冻结在决策时刻。'}
            (DIRECTORY/(c['id']+'.json')).write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            (DIRECTORY/(c['id']+'-planning.json')).write_text(json.dumps(knowledge,ensure_ascii=False,indent=2),encoding='utf-8')
            index.append({'id':c['id'],'title':payload['title'],'side':c['side'],'own_alive':c['features']['own_alive'],'enemy_alive':c['features']['enemy_alive'],'tick':c['tick'],'duration':c.get('duration',6)})
    (DIRECTORY/'index.json').write_text(json.dumps(index,ensure_ascii=False),encoding='utf-8')
    if (DIRECTORY/'events-private.json').exists():
        from .studio_events import enrich
        enrich()
    from .studio_references import build as build_references
    build_references()
    print(json.dumps({'clips':len(index),'map_triangles':len(mesh.tri),'map_bytes':len(binary)}))


if __name__=='__main__':build()
