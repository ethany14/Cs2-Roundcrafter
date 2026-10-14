"""Convex collision solids: segment intervals without pairing unrelated faces."""
import hashlib
import json
import re
import numpy as np
from .casebook import ROOT


def clip_planes(planes,start,end):
    start=np.asarray(start,float);direction=np.asarray(end,float)-start
    numerator=planes[:,3]-planes[:,:3]@start;denominator=planes[:,:3]@direction
    parallel=np.abs(denominator)<1e-10
    if np.any(parallel & (numerator < -1e-5)):return None
    enter,leave=0.,1.
    for n,d in zip(numerator[~parallel],denominator[~parallel]):
        if d>0:leave=min(leave,n/d)
        else:enter=max(enter,n/d)
    return (enter,leave) if leave-enter>1e-7 else None


class Solids:
    def __init__(self,path=None):
        path=path or ROOT/'data/maps/convex-solids.npz'
        self.meta=json.loads(path.with_suffix('.json').read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=self.meta['artifact_sha256']:raise ValueError('Solid artifact checksum mismatch')
        with np.load(path,allow_pickle=False) as d:
            self.planes=d['planes'];self.offsets=d['offsets'];self.bounds=d['bounds'];self.surface=d['surface'];self.attrs=d['attrs']

    def intervals(self,start,end):
        start=np.asarray(start,float);end=np.asarray(end,float)
        if not np.isfinite([start,end]).all():raise ValueError('Non-finite segment')
        candidates=np.all(self.bounds[:,0]<=np.maximum(start,end),axis=1)&np.all(self.bounds[:,1]>=np.minimum(start,end),axis=1)
        distance=float(np.linalg.norm(end-start));hits=[]
        for i in np.flatnonzero(candidates):
            tags=self.meta['collision_tags'][int(self.attrs[i])]
            if set(tags)&{'playerclip','npcclip','csgo_grenadeclip','sky'}:continue
            interval=clip_planes(self.planes[self.offsets[i]:self.offsets[i+1]],start,end)
            if interval:
                a,b=interval
                hits.append({'solid_id':int(i),'entry_fraction':float(a),'exit_fraction':float(b),
                             'thickness_units':float((b-a)*distance),'material':self.meta['surfaces'][int(self.surface[i])],
                             'collision_tags':tags,'segment_starts_inside':bool(a==0.),'segment_ends_inside':bool(b==1.)})
        return sorted(hits,key=lambda h:h['entry_fraction'])


def build():
    directory=ROOT/'data/maps';source=directory/'world-physics-raw.kv3';text=source.read_text(encoding='utf-8')
    surf_text=(directory/'current-surfaces').read_text(encoding='utf-8')
    names={}
    for block in re.findall(r'^\t\t\{\n(.*?)^\t\t\}',surf_text,re.M|re.S):
        name=re.search(r'surfacePropertyName = "([^"]+)"',block);h=re.search(r'm_nameHash = (\d+)',block)
        if name and h:names[int(h[1])]=name[1].lower()
    hashes=list(map(int,re.search(r'm_surfacePropertyHashes =\s*\[([^]]+)\]',text)[1].replace(',',' ').split()))
    surfaces=[names[h] for h in hashes]
    tail=text[text.index('\tm_collisionAttributes'):]
    tags=[re.findall(r'"([^"]+)"',re.search(r'm_InteractAsStrings =\s*\[([^]]*)\]',b)[1]) for b in re.findall(r'^\t\t\{\n(.*?)^\t\t\}',tail,re.M|re.S)]
    planes=[];offsets=[0];bounds=[];surface=[];attrs=[];errors=[]
    pattern=r'^\t{6}m_nCollisionAttributeIndex = (\d+)\n\t{6}m_nSurfacePropertyIndex = (\d+)\n.*?^\t{6}m_Hull =\s*\n\t{6}\{\n(.*?)^\t{6}\}'
    # Limit the match to hull records, never consume a later mesh record.
    hull_section=text[:text.index('\t\t\t\tm_meshes')]
    for idx,m in enumerate(re.finditer(pattern,hull_section,re.M|re.S)):
        body=m[3]
        def binary(field,width):
            v=re.search(r'^\t{7}'+field+r' =\s*#\[([^]]*)\]',body,re.M)[1]
            return np.frombuffer(bytes.fromhex(v),dtype='<f4').reshape(-1,width).astype(float)
        p=binary('m_Planes',4);vertices=binary('m_VertexPositions',3)
        residual=float(np.max(vertices@p[:,:3].T-p[:,3]))
        if not np.isfinite(p).all() or residual>.03:errors.append({'hull':idx,'max_outside':residual});continue
        lo=np.fromstring(re.search(r'm_vMinBounds = \[([^]]+)\]',body)[1],sep=',')
        hi=np.fromstring(re.search(r'm_vMaxBounds = \[([^]]+)\]',body)[1],sep=',')
        if np.any(vertices<lo-.03) or np.any(vertices>hi+.03):raise ValueError('Hull bounds mismatch')
        planes.append(p);offsets.append(offsets[-1]+len(p));bounds.append([lo,hi]);attrs.append(int(m[1]));surface.append(int(m[2]))
    if not planes:raise ValueError('No convex hulls imported')
    dest=directory/'convex-solids.npz'
    np.savez_compressed(dest,planes=np.concatenate(planes),offsets=offsets,bounds=bounds,surface=surface,attrs=attrs)
    meta={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'surfaces':surfaces,'collision_tags':tags,
          'artifact_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
          'hulls':len(planes),'rejected':errors,'coverage':'convex hulls only; triangle mesh solids not reconstructed'}
    dest.with_suffix('.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in meta.items() if k not in ('surfaces','collision_tags')}))


if __name__=='__main__':build()
