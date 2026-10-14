"""Demo-time door states, with deletion and serial-number identity preserved."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import numpy as np


def at_tick(events,tick):
    result={}
    for row in events:
        if row['tick']>tick:continue
        if row['kind']=='door_delete':result.pop(row['entity'],None)
        elif row['kind']=='door':result[row['entity']]=row
    return list(result.values())


def posed_mesh(local_triangles,pose):
    """Place the intact local collision model using the observed hinge pose.

    Does not reconstruct broken panels; reject unsupported pitch/roll.
    """
    from .geometry import Mesh
    pitch,yaw,roll=pose['rotation']
    if abs(pitch)>1e-4 or abs(roll)>1e-4:raise ValueError('Non-yaw door rotation not supported')
    angle=np.deg2rad(yaw);c,s=np.cos(angle),np.sin(angle)
    rotation=np.array([[c,-s,0],[s,c,0],[0,0,1]])
    return Mesh(np.asarray(local_triangles)@rotation.T+np.asarray(pose['origin']))


def export(demo,source,target):
    events=[]
    with source.open(encoding='utf-8') as f:
        for line in f:
            row=json.loads(line)
            if row['kind'] in ('door','door_delete'):events.append(row)
    events.sort(key=lambda r:r['tick'])
    with demo.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    report={'demo_sha256':digest,'source':str(source),
            'state_update_counts':dict(Counter(e['pose']['state'] for e in events if e['kind']=='door')),
            'deletions':sum(e['kind']=='door_delete' for e in events),'events':events,
            'limits':'Global entity state; not evidence the player saw or heard a door. Deletion does not by itself prove destruction.'}
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='events'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('demo',type=Path);p.add_argument('source',type=Path);p.add_argument('target',type=Path)
    a=p.parse_args();export(a.demo,a.source,a.target)
