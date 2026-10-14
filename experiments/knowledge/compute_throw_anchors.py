import json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];FILE=ROOT/'data/knowledge/metastack/teaching.json'
def ray_hit(tri,origin,direction):
 e1=tri[:,1]-tri[:,0];e2=tri[:,2]-tri[:,0];h=np.cross(direction,e2);det=np.sum(e1*h,axis=1);valid=np.abs(det)>1e-8;inv=np.zeros_like(det);inv[valid]=1/det[valid];s=origin-tri[:,0];u=inv*np.sum(s*h,axis=1);q=np.cross(s,e1);v=inv*np.sum(direction*q,axis=1);t=inv*np.sum(e2*q,axis=1);ok=valid&(u>=0)&(v>=0)&(u+v<=1)&(t>1)&(t<8000)
 return (origin+direction*float(t[ok].min())).tolist() if ok.any() else None
def anchor(actor,throw_tick):
 before=[r for r in actor if r['tick']<=throw_tick];stable=[]
 for i,r in enumerate(before):
  seg=[x for x in before[:i+1] if r['tick']-16<=x['tick']<=r['tick']]
  if len(seg)>=17 and max(math.dist(x['position'],r['position']) for x in seg)<2:stable.append(r)
 return stable[-1] if stable else None
def main():
 data=json.loads(FILE.read_text());mesh=np.load(ROOT/'data/maps/all/de_nuke/scene.npz');meta=json.loads((ROOT/'data/maps/all/de_nuke/scene.json').read_text());excluded=[i for i,g in enumerate(meta['groups']) if g.get('SurfaceProperty')=='audioblocker'];tri=mesh['triangles'][~np.isin(mesh['groups'],excluded)].reshape(-1,3,3).astype(float)
 for c in data['cases'].values():
  rows=c['actor'];a=anchor(rows,c['throw_tick']);r=min(rows,key=lambda x:abs(x['tick']-c['throw_tick']));prev=min(rows,key=lambda x:abs(x['tick']-(c['throw_tick']-8)));dt=(r['tick']-prev['tick'])/64
  horizontal=math.dist(r['position'][:2],prev['position'][:2])/dt if dt>0 else None
  pitch,yaw=map(math.radians,[r['pitch'],r['yaw']]);direction=np.array([math.cos(pitch)*math.cos(yaw),math.cos(pitch)*math.sin(yaw),-math.sin(pitch)])
  duck=r.get('duck');eye=np.array(r['position'])+[0,0,64-18*(duck or 0)];hit=ray_hit(tri,eye,direction)
  c['anchors']={'stable_before_throw':a,'stable_rule':'连续 17 tick，位置变化 <2 单位；最多回看 2 秒，不代表已验证 lineup 起点','horizontal_speed':horizontal,'aim_surface_point':hit,'eye_height_model':'64-18*duckAmount，近似眼高；动态门、贴图特征和第一人称视图偏移未恢复','method_inference':'moving' if horizontal and horizontal>20 else 'near_stationary','practice_verified':False}
 FILE.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');print(json.dumps({'cases':len(data['cases']),'method_fields':sum(c.get('method',{}).get('status')=='observed_active_grenade_fields' for c in data['cases'].values()),'stable_anchors':sum(c['anchors']['stable_before_throw'] is not None for c in data['cases'].values()),'ray_hits':sum(c['anchors']['aim_surface_point'] is not None for c in data['cases'].values())}))
if __name__=='__main__':main()
