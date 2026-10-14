"""Network smoke occupancy, not rendered opacity.

Wire-format reference: demolens v2.5.0, internal/parser/smokevoxel.go,
Copyright (c) 2026 Florian Gillmann, MIT (docs/third-party/demolens-LICENSE.txt).
12-unit grid mapping and interior fill are community-derived assumptions.
"""
import argparse
import base64
import hashlib
import json
import re
import sqlite3
import struct
import zlib
from functools import lru_cache
import numpy as np
from .casebook import ROOT

DATABASE = ROOT/'data/maps/smoke-frames.sqlite'


def demorton(value, bits):
    return tuple(sum(((value >> (3*b+a)) & 1) << b for b in range(bits)) for a in range(3))


@lru_cache(maxsize=128)
def decode(data):
    """Strictly decode a complete cumulative stream; reject unsupported layouts."""
    pos=0; sequence=None; seeds=[]; masks={}; ready=False; phase=0; chunks=0
    while pos < len(data):
        if pos+4>len(data): raise ValueError('Truncated chunk header')
        seq,size=struct.unpack_from('<HH',data,pos);pos+=4
        if sequence is not None and seq != (sequence+1)%65536: raise ValueError('Non-contiguous chunk sequence')
        sequence=seq
        payload=data[pos:pos+size];pos+=size
        if len(payload)!=size or size<3: raise ValueError('Truncated chunk payload')
        phase,kind=payload[:2];offset=2
        if phase not in (0,1): raise ValueError('Unknown smoke phase')
        if kind==3:
            seeds=[];masks={};count=payload[2];offset=3
            if offset+count*8+2>size: raise ValueError('Truncated seeds')
            for i in range(count):
                x,y,z,density=payload[offset:offset+4];offset+=8
                if max(x,y,z)>=32: raise ValueError('Seed outside grid')
                if density: seeds.append((x,y,z))
            ready=True
        if kind in (2,3):
            if not ready: raise ValueError('Delta without keyframe')
            count=struct.unpack_from('<H',payload,offset)[0];offset+=2
            if offset+10*count>size: raise ValueError('Truncated masks')
            for i in range(count):
                cell,mask=struct.unpack_from('<HQ',payload,offset);offset+=10
                if cell>=512: raise ValueError('Cell outside grid')
                masks[cell]=mask
        elif kind!=0: raise ValueError('Unknown chunk type')
        if payload[offset:] != b'\0': raise ValueError('Unexpected payload trailer')
        chunks+=1
    if not ready: raise ValueError('No keyframe')
    grid=np.zeros((32,32,32),bool)
    for seed in seeds:grid[seed]=True
    for cell,mask in masks.items():
        cell_xyz=np.array(demorton(cell,3))*4
        for bit in range(64):
            if mask>>bit&1:grid[tuple(cell_xyz+demorton(bit,2))]=True
    shell_count=int(grid.sum())
    # Six-connected exterior flood; filled interior is an explicit inference.
    outside=np.zeros_like(grid)
    outside[[0,-1],:,:]=True;outside[:,[0,-1],:]=True;outside[:,:,[0,-1]]=True
    outside &= ~grid
    while True:
        expanded=outside.copy()
        expanded[1:,:,:]|=outside[:-1,:,:];expanded[:-1,:,:]|=outside[1:,:,:]
        expanded[:,1:,:]|=outside[:,:-1,:];expanded[:,:-1,:]|=outside[:,1:,:]
        expanded[:,:,1:]|=outside[:,:,:-1];expanded[:,:,:-1]|=outside[:,:,1:]
        expanded &= ~grid
        if np.array_equal(expanded,outside):break
        outside=expanded
    grid=~outside
    cells=np.argwhere(grid).astype(float);cells.flags.writeable=False
    return cells,{'chunks':chunks,'phase_flag':phase,'network_seed_and_mask_voxels':shell_count,
                  'filled_voxels':len(cells),'interior_fill':'six_connected_complement_inference'}


def raycast(frame,start,end):
    data=base64.b64decode(frame['data_base64'],validate=True)
    try: cells,info=decode(data)
    except (ValueError,struct.error) as error:
        return {'status':'decode_failed','reason':str(error),'frame_tick':frame['tick']}
    origin=(np.asarray(start,float)-frame['position'])/12+16
    direction=(np.asarray(end,float)-np.asarray(start,float))/12
    near=np.zeros(len(cells));far=np.ones(len(cells));valid=np.ones(len(cells),bool)
    for axis in range(3):
        if abs(direction[axis])<1e-12:
            valid &= (origin[axis]>=cells[:,axis]) & (origin[axis]<cells[:,axis]+1)
        else:
            a=(cells[:,axis]-origin[axis])/direction[axis];b=a+1/direction[axis]
            near=np.maximum(near,np.minimum(a,b));far=np.minimum(far,np.maximum(a,b))
    hit=valid & (far>near)
    return {'status':'network_occupancy_decoded','frame_tick':frame['tick'],**info,
            'intersects':bool(hit.any()),'path_units':float(np.sum((far-near)[hit])*np.linalg.norm(direction)*12),
            'grid_cell_units':12,'grid_mapping':'community_derived_not_render_calibrated',
            'opacity':'unknown; occupancy and inferred interior do not reproduce rendering, bullet holes or HE clearing'}


def frames_for_case(case):
    smokes=[dict(s) for s in case['evidence'].get('smokes',[])]
    if not DATABASE.exists():return smokes
    with sqlite3.connect(DATABASE) as db:
        for smoke in smokes:
            row=db.execute('SELECT tick,position,payload FROM frames WHERE demo_hash=? AND entity_index=? AND tick BETWEEN ? AND ? ORDER BY tick DESC LIMIT 1',
                           (case.get('demo_sha256',''),smoke.get('entity_id'),smoke['start_tick'],case['tick'])).fetchone()
            if row:
                smoke['voxel_frame']={'tick':row[0],'position':json.loads(row[1]),
                                       'data_base64':base64.b64encode(zlib.decompress(row[2])).decode()}
    return smokes


def import_frames(demo,path):
    digest=hashlib.file_digest(open(demo,'rb'),'sha256').hexdigest()
    counts={'frames':0,'decoded':0,'failed':0}; errors=[]
    with sqlite3.connect(DATABASE) as db:
        db.execute('CREATE TABLE IF NOT EXISTS frames(demo_hash TEXT,entity_index INTEGER,serial INTEGER,tick INTEGER,position TEXT,payload BLOB,PRIMARY KEY(demo_hash,entity_index,serial,tick))')
        db.execute('CREATE INDEX IF NOT EXISTS lookup ON frames(demo_hash,entity_index,tick)')
        for line in open(path,encoding='utf-8'):
            row=json.loads(line)
            if row['kind']!='smoke':continue
            data=base64.b64decode(row['data_base64']);size=row['declared_size'];counts['frames']+=1
            if not 0<size<=len(data):raise ValueError('Invalid declared payload size')
            data=data[:size]
            try:decode(data);counts['decoded']+=1
            except (ValueError,struct.error) as error:
                counts['failed']+=1
                if len(errors)<10:errors.append({'tick':row['tick'],'reason':str(error)})
            entity,serial=map(int,re.fullmatch(r'Index = (\d+), Serial = (\d+)',row['entity']).groups())
            db.execute('INSERT OR REPLACE INTO frames VALUES(?,?,?,?,?,?)',(digest,entity,serial,row['tick'],json.dumps(row['detonation_position']),zlib.compress(data)))
    report={'demo_sha256':digest,'source_jsonl':str(path),'counts':counts,'errors':errors,
            'validation':'format consistency only; no rendered opacity ground truth'}
    (ROOT/'outputs/casebook'/f'{demo.stem}-voxel-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('demo',type=Path);p.add_argument('frames',type=Path)
    args=p.parse_args();import_frames(args.demo,args.frames)
