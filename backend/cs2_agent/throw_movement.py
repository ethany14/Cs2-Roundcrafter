"""Experimental movement profiles; source measurements and product assumptions separated."""
import math
import numpy as np
from .grenade_search import PARAMS,JUMP_PROFILE,jump_release,standable,first_hit

LABELS={'stand_left':'站立投掷','jump_left':'原地跳投','w_jump_left':'W 点按跳投',
        'crouch_jump_left':'蹲稳跳投','run_jump_left':'助跑跳投'}
MOVEMENT_EVIDENCE={
 'sources':['https://memorin.app/mechanics/air-acceleration','https://memorin.app/mechanics/movement-constants','https://memorin.app/mechanics/jump-throw'],
 'source_parameters':{'air_acceleration':12.,'air_wish_cap':30.,'ground_acceleration':5.5,'friction':5.2,'stop_speed':80.,'crouched_hull':54.,'crouch_vz_offset':3.125},
 'assumptions':{'grenade_run_speed':250.,'surface_friction':1.,'crouch_eye_height':46.,'w_tap_seconds':1/64,'movement_step':1/256},
 'status':'experimental_not_locally_calibrated','limits':['平地直线助跑；不处理坡道、台阶、转向和起跳前跳跃疲劳','W 点按按一个 64 Hz tick 建模，实际按键时序有误差','蹲稳后一直保持蹲姿；不模拟起跳过程中按蹲的姿态过渡']}

def movement_release(m,pos,yaw,mode,run_distance=128.,checkpoint=lambda:None):
    p=np.asarray(pos,float);angle=math.radians(yaw);forward=np.array([math.cos(angle),math.sin(angle),0.])
    crouched=mode=='crouch_jump_left';hull=54. if crouched else 72.;eye=46. if crouched else 64.
    jump_point=p.copy();ground_path=[p.tolist()];speed=0.;distance=0.;elapsed=0.;dt=1/256
    if mode=='run_jump_left':
        # Integrate straight grounded acceleration and friction from rest.
        next_probe=0.
        while distance<run_distance:
            checkpoint()
            speed=max(0.,speed-max(speed,80.)*5.2*dt)
            speed=min(250.,speed+5.5*250.*dt)
            step=min(speed*dt,run_distance-distance)
            distance+=step;elapsed+=dt;q=p+forward*distance
            if distance>=next_probe or distance>=run_distance:
                if not standable(m,q):return None
                for z in [18.,36.,54.]:
                    from .projectile_collision import sweep
                    if sweep(m,jump_point+[0,0,z],q+[0,0,z],16.):return None
                ground_path.append(q.tolist());jump_point=q;next_probe=distance+8.
            if elapsed>5:return None
    elif mode=='w_jump_left':
        # Simultaneous takeoff + one short forward input, not a ground run-up.
        speed=0.
    t=0.;travel=0.;air_path=[jump_point.tolist()]
    while t<JUMP_PROFILE['latch_seconds']-1e-9:
        checkpoint();step=min(dt,JUMP_PROFILE['latch_seconds']-t)
        if mode=='w_jump_left' and t<1/64:
            speed+=min(max(0.,30.-speed),12.*250.*step)
        travel+=speed*step;t+=step
        dz=JUMP_PROFILE['takeoff_vz']*t-.5*800.*t*t
        q=jump_point+forward*travel+[0,0,dz]
        prev=np.asarray(air_path[-1])
        for dx,dy in [(0,0),(-16,-16),(-16,16),(16,-16),(16,16)]:
            if first_hit(m,prev+[dx,dy,hull],q+[dx,dy,hull]):return None
        if mode in ('w_jump_left','run_jump_left'):
            from .projectile_collision import sweep
            for z in [18.,hull/2,hull-2]:
                if sweep(m,prev+[0,0,z],q+[0,0,z],16.):return None
        air_path.append(q.tolist())
    vz=JUMP_PROFILE['latched_player_vz']+(3.125 if crouched else 0.)
    added=forward*speed*1.25+[0,0,vz*1.25]
    return {'height_offset':dz,'added_vz':vz*1.25,'added_velocity':added.tolist(),
            'release_feet':(jump_point+forward*travel).tolist(),'eye_height':eye,
            'jump_point':jump_point.tolist(),'ground_path':ground_path,'air_path':air_path,
            'run_distance':distance,'run_seconds':round(elapsed,4),'player_horizontal_speed':speed,
            'movement_yaw':yaw,'profile':MOVEMENT_EVIDENCE,'height_evidence':'continuous_motion_inference'}

def execution_steps(c):
    mode=c['mode'];steps=['在绿色起点站定，按给定角度瞄准','按住左键准备烟雾弹']
    if mode=='stand_left':steps+=['保持静止，松开左键']
    elif mode=='jump_left':steps+=['原地起跳并松开左键，保持瞄准方向']
    elif mode=='w_jump_left':steps+=['起跳同时点按一下 W 并松开左键；不要预先移动，不要持续按 W','实验按键模型约 16 毫秒；实际点按时序需实投校准']
    elif mode=='crouch_jump_left':steps+=['先按住蹲键等待蹲稳，再起跳并松开左键；整个动作保持蹲键']
    elif mode=='run_jump_left':
        a=c['launch_assumptions'];point=', '.join(f'{v:.1f}' for v in a['jump_point'])
        steps+=[f"沿当前瞄准方向按住 W，直线助跑 {a['run_distance']:.0f} 单位（模型约 {a['run_seconds']:.2f} 秒）",
                f'到橙色起跳点 [{point}] 时起跳并松开左键，保持 W 与瞄准方向','按空间标记起跳，时间仅供参考；不要开局已有速度或中途转向']
    return steps
