"""Continuous sphere/triangle sweep; independent geometry, not an engine hull claim."""
import numpy as np


def candidate_triangles(mesh,a,b,radius):
 lo=np.minimum(a,b)-radius;hi=np.maximum(a,b)+radius;stack=[0];ids=[]
 while stack:
  nlo,nhi,left,right=mesh.nodes[stack.pop()]
  if np.any(nlo>hi) or np.any(nhi<lo):continue
  if right is None:ids.extend(left)
  else:stack.extend((left,right))
 return np.asarray(ids,dtype=int)


def sweep(mesh,start,end,radius=2.):
 a=np.asarray(start,float);d=np.asarray(end,float)-a
 if a.shape!=(3,) or d.shape!=(3,) or not np.isfinite([a,d]).all() or not np.isfinite(radius) or radius<=0:raise ValueError('Invalid sweep')
 if np.linalg.norm(d)<1e-12:return None
 ids=candidate_triangles(mesh,a,a+d,radius)
 if not len(ids):return None
 tri=mesh.tri[ids];candidates=[]
 def record(ts,normals,valid,kind):
  valid=valid&np.isfinite(ts)&(ts>=-1e-8)&(ts<=1+1e-8)&(np.einsum('ij,j->i',normals,d)<-1e-9)
  if valid.any():
   rows=np.flatnonzero(valid);k=rows[np.argmin(ts[rows])];candidates.append({'fraction':float(max(0,ts[k])),'normal':normals[k],'triangle':int(ids[k]),'feature':kind})
 # Face offset planes, two-sided. The contact must lie inside the triangle.
 e0=tri[:,1]-tri[:,0];e1=tri[:,2]-tri[:,0];n=np.cross(e0,e1);length=np.linalg.norm(n,axis=1);n=np.divide(n,length[:,None],out=np.zeros_like(n),where=length[:,None]>1e-12)
 dist=np.einsum('ij,ij->i',a-tri[:,0],n);den=n@d
 for side in [-1,1]:
  t=np.divide(side*radius-dist,den,out=np.full(len(ids),np.inf),where=np.abs(den)>1e-12)
  safe=np.where(np.isfinite(t),t,0);q=a+safe[:,None]*d-side*radius*n;rel=q-tri[:,0]
  dot00=np.einsum('ij,ij->i',e0,e0);dot01=np.einsum('ij,ij->i',e0,e1);dot11=np.einsum('ij,ij->i',e1,e1);dot20=np.einsum('ij,ij->i',rel,e0);dot21=np.einsum('ij,ij->i',rel,e1);det=dot00*dot11-dot01**2
  u=np.divide(dot11*dot20-dot01*dot21,det,out=np.zeros(len(ids)),where=det>1e-12);v=np.divide(dot00*dot21-dot01*dot20,det,out=np.zeros(len(ids)),where=det>1e-12)
  record(t,n*side,(length>1e-12)&(u>=-1e-8)&(v>=-1e-8)&(u+v<=1+1e-8),'face')
 def quadratic(w,velocity,kind,edge=None,base=None):
  aa=np.einsum('ij,ij->i',velocity,velocity);bb=2*np.einsum('ij,ij->i',w,velocity);cc=np.einsum('ij,ij->i',w,w)-radius**2;disc=bb**2-4*aa*cc
  t=np.divide(-bb-np.sqrt(np.maximum(0,disc)),2*aa,out=np.full(len(ids),np.inf),where=aa>1e-12);safe=np.where(np.isfinite(t),t,0);normal=w+safe[:,None]*velocity;ln=np.linalg.norm(normal,axis=1);normal=np.divide(normal,ln[:,None],out=np.zeros_like(normal),where=ln[:,None]>1e-12);valid=(disc>=0)&(aa>1e-12)
  if edge is not None:
   lens=np.einsum('ij,ij->i',edge,edge);along=np.divide(np.einsum('ij,ij->i',a+safe[:,None]*d-base,edge),lens,out=np.zeros(len(ids)),where=lens>1e-12);valid&=(lens>1e-12)&(along>=0)&(along<=1)
  record(t,normal,valid,kind)
 for k in range(3):
  base=tri[:,k];edge=tri[:,(k+1)%3]-base;lens=np.einsum('ij,ij->i',edge,edge);rel=a-base
  wp=np.divide(np.einsum('ij,ij->i',rel,edge),lens,out=np.zeros(len(ids)),where=lens>1e-12);dp=np.divide(edge@d,lens,out=np.zeros(len(ids)),where=lens>1e-12)
  quadratic(rel-edge*wp[:,None],np.broadcast_to(d,edge.shape)-edge*dp[:,None],'edge',edge,base)
  quadratic(rel,np.broadcast_to(d,edge.shape),'vertex')
 return min(candidates,key=lambda h:h['fraction']) if candidates else None


def advance(mesh,position,velocity,dt,gravity=320.,radius=2.,elasticity=.45):
 """Consume remaining tick time after contact, bounded to four contacts."""
 x=np.asarray(position,float).copy();v=np.asarray(velocity,float).copy();remaining=dt;events=[]
 if not np.isfinite([x,v]).all() or not 0<dt<=.1:raise ValueError('Invalid state')
 g=np.array([0.,0.,-gravity])
 for _ in range(4):
  end=x+v*remaining+g*remaining**2/2;h=sweep(mesh,x,end,radius)
  if h is None:x=end;v+=g*remaining;remaining=0;break
  elapsed=remaining*h['fraction'];x=x+(end-x)*h['fraction'];v+=g*elapsed;normal=h['normal'];impact=abs(float(v@normal));v=(v-2*(v@normal)*normal)*elasticity;x+=normal*.01;remaining-=elapsed
  events.append({'normal':normal.tolist(),'impact':impact,'feature':h['feature'],'triangle':h['triangle']})
  if normal[2]>.7 and np.linalg.norm(v)<35:return x,np.zeros(3),events,True,False
  if remaining<1e-9:break
 return x,v,events,False,remaining>1e-9
