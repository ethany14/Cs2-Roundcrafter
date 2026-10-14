"""Repeatable local diagnostics; no AI calls or visual-accuracy claims."""
import json
import sqlite3
import struct
import zlib
from collections import Counter
import numpy as np
from cs2_agent.casebook import ROOT
from cs2_agent.map_assets import load_scene
from cs2_agent.solid_geometry import clip_planes
from cs2_agent.smoke_voxels import DATABASE,decode


def smoke_audit():
    counts=Counter();examples=[];previous={}
    with sqlite3.connect(DATABASE) as db:
        # Final network sample of each entity lifecycle; not a rendered final frame.
        rows=db.execute('SELECT demo_hash,entity_index,serial,tick,payload FROM frames ORDER BY demo_hash,entity_index,serial,tick')
        def check(row):
            if row is None:return
            data=zlib.decompress(row[4]);cells,info=decode(data);counts['clouds']+=1
            if info['phase_flag']:
                counts['final_phase_nonzero']+=1;counts['nonzero_phase_still_occupied']+=bool(len(cells))
                if len(examples)<5:examples.append({'demo_hash':row[0],'entity_index':row[1],'serial':row[2],'tick':row[3],**info})
        last=None
        for row in rows:
            if last and row[:3]!=last[:3]:check(last)
            last=row
        check(last)
    return {'counts':dict(counts),'examples':examples,'conclusion':'Final occupancy can remain nonempty in fade phase; occupancy cannot determine rendered transparency.'}


def hull_audit():
    mesh=load_scene();solids=mesh.solids;rows=[]
    for i in np.linspace(0,len(solids.bounds)-1,100,dtype=int):
        tags=solids.meta['collision_tags'][int(solids.attrs[i])]
        if tags:continue
        lo,hi=solids.bounds[i];center=(lo+hi)/2;axis=int(np.argmax(hi-lo))
        start=center.copy();end=center.copy();start[axis]=lo[axis]-10;end[axis]=hi[axis]+10
        result=clip_planes(solids.planes[solids.offsets[i]:solids.offsets[i+1]],start,end)
        if not result:continue
        hits=mesh.intersections(start,end,limit=10000);length=float(np.linalg.norm(end-start))
        errors=[min((abs(h['fraction']-t)*length for h in hits),default=None) for t in result]
        rows.append({'solid_id':int(i),'endpoint_errors_units':errors,'both_within_0_05_units':all(e is not None and e<=.05 for e in errors)})
    return {'samples':len(rows),'both_endpoints_match':sum(r['both_within_0_05_units'] for r in rows),'rows':rows,
            'limits':'Sample consistency with independently exported triangle geometry, not bullet-path accuracy or complete map-solid coverage.'}


report={'smoke':smoke_audit(),'hulls':hull_audit()}
(ROOT/'outputs/casebook/physics-consistency-validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'smoke':report['smoke']['counts'],'hulls':{k:v for k,v in report['hulls'].items() if k!='rows'}}))
