"""Lifecycle-aware smoke evidence; dynamic voxel opacity remains unknown."""
import math
import numpy as np


def cylinder_interval(start,end,center,radius=200.,bottom=-40.,top=180.):
    """Exact finite-segment/cylinder interval, including vertical and tangent rays."""
    a=np.asarray(start,float)-center;d=np.asarray(end,float)-start
    if not np.isfinite(a).all() or not np.isfinite(d).all():return None
    lower,upper=0.,1.
    if abs(d[2])<1e-12:
        if not bottom<=a[2]<=top:return None
    else:
        lo,hi=sorted(((bottom-a[2])/d[2],(top-a[2])/d[2]));lower=max(lower,lo);upper=min(upper,hi)
    A=float(d[:2]@d[:2]);B=2*float(a[:2]@d[:2]);C=float(a[:2]@a[:2])-radius**2
    if A<1e-12:
        if C>0:return None
    else:
        disc=B*B-4*A*C
        if disc<0:return None
        root=math.sqrt(disc);lower=max(lower,(-B-root)/(2*A));upper=min(upper,(-B+root)/(2*A))
    return (lower,upper) if lower<=upper else None


def assess(start,end,smokes,tick,rate=64,disturbances=None):
    overlaps=[];disturbances=disturbances or {};voxel_results=[]
    for smoke in smokes:
        if smoke['start_tick']>tick or (smoke.get('expired_tick') is not None and smoke['expired_tick']<=tick):continue
        frame=smoke.get('voxel_frame')
        if frame and smoke['start_tick']<=frame['tick']<=tick:
            from .smoke_voxels import raycast
            voxel_results.append({'entity_id':smoke.get('entity_id'),**raycast(frame,start,end)})
        interval=cylinder_interval(start,end,np.asarray(smoke['position']))
        if interval is None:continue
        age=(tick-smoke['start_tick'])/rate
        alerts=[]
        for he in disturbances.get('he',[]):
            if smoke['start_tick']<=he['tick']<=tick and 0<=(tick-he['tick'])/rate<=2 and np.linalg.norm(np.asarray(he['position'])-smoke['position'])<=500:
                alerts.append({'type':'nearby_HE_possible_displacement','tick':he['tick'],'calibration':'500-unit/2-second candidate window, not a smoke clearing rule'})
        for shot in disturbances.get('shots',[]):
            if not (smoke['start_tick']<=shot['tick']<=tick and (tick-shot['tick'])/rate<=1):continue
            if not all(isinstance(x,(int,float)) for x in shot['origin']+shot['angles']):continue
            pitch,yaw=np.deg2rad(shot['angles']);forward=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),-np.sin(pitch)])
            origin=np.asarray(shot['origin'])
            if cylinder_interval(origin,origin+8192*forward,np.asarray(smoke['position'])) is not None:
                alerts.append({'type':'shot_direction_intersects_smoke_envelope','tick':shot['tick'],'calibration':'spread and bullet holes not reconstructed'})
        updates=[u for u in smoke.get('voxel_updates',[]) if u['tick']<=tick]
        overlaps.append({'entity_id':smoke.get('entity_id'),'start_tick':smoke['start_tick'],'age_seconds':age,
                         'segment_length_in_envelope':float((interval[1]-interval[0])*np.linalg.norm(np.asarray(end)-start)),
                         'phase':'early_growth_uncertain' if age<1.5 else 'active_lifecycle',
                         'latest_voxel_update':updates[-1] if updates else None,'disturbances':alerts,
                         'opacity':'unknown; envelope overlap is not proof of blocked vision'})
    status='no_envelope_overlap' if not overlaps else ('disturbed_opacity_unknown' if any(o['disturbances'] for o in overlaps) else 'potential_smoke_occlusion')
    return {'status':status,'overlaps':overlaps,'volume_reconstructed':False,
            'network_voxel_evidence':voxel_results,
            'network_occupancy_available':any(v['status']=='network_occupancy_decoded' for v in voxel_results),
            'model':'provisional 200-unit radius envelope; not clipped to map or calibrated to volumetric smoke'}
