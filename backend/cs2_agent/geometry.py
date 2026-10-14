"""Independent static mesh segment tests. Never infer rendered visibility from a ray alone."""
import hashlib
import numpy as np


class Mesh:
    def __init__(self, triangles):
        self.tri=np.asarray(triangles,dtype=np.float64)
        if self.tri.ndim!=3 or self.tri.shape[1:]!=(3,3) or not np.isfinite(self.tri).all():
            raise ValueError('Invalid triangles')
        self.nodes=[]
        centers=self.tri.mean(axis=1)
        def build(ids):
            idx=len(self.nodes);lo=self.tri[ids].min(axis=(0,1));hi=self.tri[ids].max(axis=(0,1))
            self.nodes.append(None)
            if len(ids)<=48:self.nodes[idx]=(lo,hi,ids,None)
            else:
                axis=int(np.argmax(hi-lo));order=ids[np.argsort(centers[ids,axis])];mid=len(order)//2
                self.nodes[idx]=(lo,hi,build(order[:mid]),build(order[mid:]))
            return idx
        build(np.arange(len(self.tri)))

    @classmethod
    def from_obj(cls,path):
        vertices=[];faces=[]
        with open(path,encoding='utf-8') as f:
            for line in f:
                if line.startswith('v '):vertices.append(list(map(float,line.split()[1:4])))
                elif line.startswith('f '):
                    face=[int(s.split('/')[0]) for s in line.split()[1:]]
                    face=[i-1 if i>0 else len(vertices)+i for i in face]
                    faces.extend((face[0],face[i],face[i+1]) for i in range(1,len(face)-1))
        # CS-NET OBJ convention: (gameY, gameZ, gameX) * 0.0254.
        vertices=np.asarray(vertices)[:,[2,0,1]]/.0254
        mesh=cls(vertices[np.asarray(faces)])
        mesh.sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        return mesh

    def intersections(self,start,end,limit=32):
        o=np.asarray(start,float);d=np.asarray(end,float)-o
        if not np.isfinite(o).all() or not np.isfinite(d).all():raise ValueError('Invalid ray')
        if np.linalg.norm(d)<1e-6:return []
        stack=[0];hits=[]
        while stack:
            lo,hi,left,right=self.nodes[stack.pop()];near=0.;far=1.;hit=True
            for ax in range(3):
                if abs(d[ax])<1e-12:
                    if o[ax]<lo[ax] or o[ax]>hi[ax]:hit=False;break
                else:
                    a,b=sorted(((lo[ax]-o[ax])/d[ax],(hi[ax]-o[ax])/d[ax]))
                    near=max(near,a);far=min(far,b)
                    if near>far:hit=False;break
            if not hit:continue
            if right is not None:stack.extend((left,right));continue
            tri=self.tri[left];e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0]
            h=np.cross(np.broadcast_to(d,e2.shape),e2);det=np.einsum('ij,ij->i',e1,h)
            valid=abs(det)>1e-9;inv=np.divide(1.,det,out=np.zeros_like(det),where=valid)
            s=o-tri[:,0];u=inv*np.einsum('ij,ij->i',s,h);q=np.cross(s,e1)
            v=inv*np.einsum('j,ij->i',d,q);t=inv*np.einsum('ij,ij->i',e2,q)
            mask=valid&(u>=0)&(v>=0)&(u+v<=1)&(t>1e-5)&(t<1-1e-5)
            for i in np.where(mask)[0]:hits.append((float(t[i]),int(left[i])))
        hits.sort()
        # Coincident triangles of the same surface produce one crossing.
        unique=[]
        for t,index in hits:
            metadata=self.surfaces[int(self.surface_ids[index])] if hasattr(self,'surface_ids') else {'SurfaceProperty':'unknown'}
            if unique and abs(t-unique[-1]['fraction'])<1e-6 and metadata==unique[-1]['surface']:continue
            unique.append({'fraction':t,'distance_units':t*float(np.linalg.norm(d)),'triangle':index,'surface':metadata})
        return unique[:limit]

    def blocked(self,start,end):
        return bool(self.intersections(start,end,limit=1))


def eye(player):
    duck=player.get('duck_amount')
    height=64-18*min(1,max(0,duck)) if isinstance(duck,(int,float)) else 64
    return np.asarray(player['position'],float)+[0,0,height]


def smoke_intersects(start,end,smokes,tick):
    from .smoke import assess
    return bool(assess(start,end,smokes,tick)['overlaps'])


def sight(mesh,observer,target,smokes,tick,rate=64,disturbances=None):
    from .smoke import assess
    origin=eye(observer);head=eye(target);chest=head-[0,0,24]
    rays=[mesh.intersections(origin,p) for p in (head,chest)]
    clear=any(not ray for ray in rays)
    surfaces=[]
    for hit in rays[0][:8]:
        metadata=hit['surface'];material=metadata.get('SurfaceProperty','unknown').lower();tags=metadata.get('InteractAs',[])
        surfaces.append({'distance_units':hit['distance_units'],'material':material,'collision_tags':tags,
                         'bullet_evidence':'explicit_passbullets_tag' if 'passbullets' in tags else 'weapon_and_thickness_required',
                         'visual_evidence':'possibly_transparent_or_perforated' if material in ('glass','chainlink') else 'surface_opacity_not_measured'})
    door_hits=mesh.doors.intersections(origin,head,limit=3) if hasattr(mesh,'doors') else []
    smoke=assess(origin,head,smokes,tick,rate,disturbances)
    direction=head-origin
    yaw=np.deg2rad(observer['yaw']);pitch=np.deg2rad(observer['pitch'])
    forward=np.array([np.cos(pitch)*np.cos(yaw),np.cos(pitch)*np.sin(yaw),-np.sin(pitch)])
    cosine=float(forward@direction/max(np.linalg.norm(direction),1e-9))
    angle=float(np.rad2deg(np.arccos(np.clip(cosine,-1,1))))
    flash=observer.get('flash_duration')
    return {'static_ray_clear':bool(clear),'aim_angle_degrees':angle,'within_approximate_view_cone':angle<=45,
            'smoke_overlap_possible':bool(smoke['overlaps']),'smoke_analysis':smoke,
            'line_of_fire':{'head_ray_crossings':surfaces,'can_penetrate':None,
                            'convex_solid_intervals':mesh.solids.intervals(origin,head) if hasattr(mesh,'solids') else [],
                            'thickness_coverage':'convex solids only; triangle-mesh solids and dynamic objects incomplete',
                            'reason':'Some solid thicknesses measured. Penetration damage hypothesis failed validation; no reliable wall damage prediction.'},
            'static_doorway_models_crossed':[{'asset':h['surface'].get('asset'),'distance_units':h['distance_units'],
                                   'entity_kind':'static_scenery', 'operable':False, 'state':'fixed_map_geometry'} for h in door_hits],
            'visibility':'not_established; collision does not imply opaque or bulletproof',
            'flash_state':('unknown' if flash is None else ('possibly_impaired' if flash>0 else 'no_duration_flag')),
            'meaning':'geometric/material evidence only; not proof of visibility, attention, bullet penetration or player knowledge'}
