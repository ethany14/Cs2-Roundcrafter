"""Join tactical slots to demo evidence using game-reported spatial labels.

Labels at effect positions are inferred from nearby observed player anchors,
not an authoritative navmesh query. Every link stays a review candidate.
"""
import json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'data/knowledge/metastack'
TARGETS=[
 dict(id='6518',name='屋顶 → Heaven 烟',kind='smoke',origin=['Roof'],destination=['Heaven'],clock=106,specific=True),
 dict(id='1370',name='屋顶 → Hut 顶火',kind='fire',origin=['Roof'],destination=['HutRoof'],clock=106,specific=True),
 dict(id='1724',name='屋顶 → A 区闪（两次）',kind='flash',origin=['Roof'],destination=['BombsiteA','Rafters','HutRoof'],clock=100,specific=False),
 dict(id='1369',name='屋顶 → Backsite 火',kind='fire',origin=['Roof'],destination=['BombsiteA'],clock=100,specific=False),
 dict(id='1362',name='T Yard → T Vent 烟',kind='smoke',origin=['Outside','TSpawn'],destination=['Vents','Squeaky','BombsiteA'],clock=110,specific=False),
 dict(id='1361',name='外场过点烟',kind='smoke',origin=['Outside','TSpawn'],destination=['Outside'],clock=110,specific=False),
]
def match(c,t,anchors):
 if c['team']!=2 or c['type']!=t['kind'] or c['release']['area'] not in t['origin']:return None
 pos=c['effect_position'];near=min(anchors,key=lambda a:math.dist(a['position'],pos))
 distance=math.dist(near['position'],pos);height=abs(near['position'][2]-pos[2])
 if near['name'] not in t['destination'] or distance>256 or height>192:return None
 gap=abs(c['clock_at_throw']-t['clock'])
 # Include timing mismatch for review, never silently retime recorded footage.
 return dict(distance=round(distance,1),height_gap=round(height,1),area=near['name'],clock_gap=round(gap,2),rank_cost=round(distance/256+gap/10,3),status='spatial_candidate_needs_review',unknown=['封锁/致盲/燃烧覆盖效果尚未确认','并非原战术 demo 对齐','赶路与后续投掷衔接尚未确认']+([] if t['specific'] else ['目标只定位到大区域，不能确认具体点位']))
def main():
 datasets=[json.loads(p.read_text()) for p in sorted((D/'extracted').glob('*.json')) if p.stem!='probe']
 anchors=[a for d in datasets for a in d['anchors']];cases=[c for d in datasets for c in d['cases']];lessons=[];selected={}
 for t in TARGETS:
  matches=[]
  for c in cases:
   m=match(c,t,anchors)
   if m:matches.append({'case_id':c['id'],**m})
  matches.sort(key=lambda m:(m['rank_cost'],m['case_id']))
  for m in matches[:3]:selected[m['case_id']]=next(c for c in cases if c['id']==m['case_id'])
  lessons.append({**t,'source_url':'https://metastack.gg/nades/'+t['id']+'-'+{'6518':'heaven-a-site-from-roof','1370':'top-hut-from-roof','1724':'a-site-from-roof','1369':'backsite-from-roof','1362':'t-vent-from-t-yard','1361':'outside-cross-smoke'}[t['id']],'candidates':matches[:3],'total_candidates':len(matches),'status':'candidates' if matches else 'missing'})
 for id,name,kind in [('loose_he','破门雷（手抛）','he'),('loose_smoke','管道反弹烟（手抛）','smoke'),('loose_fire','管道火（手抛）','fire'),('loose_flash','管道右键闪（手抛）','flash')]:
  lessons.append(dict(id=id,name=name,kind=kind,specific=False,candidates=[],total_candidates=0,status='missing',source_url='https://metastack.gg/strats/64994-gl-a-fake-to-ramp-pop-forcebuy',reason='资料未给独立投掷条目；目标锚点尚未标定'))
 out={'schema':1,'map':'de_nuke','tactic_id':'metastack-64994','demo_count':len(datasets),'observed_throw_count':len(cases),'lessons':lessons,'cases':selected,'method':'T-side + type + release nav label + nearest observed nav anchor in 3D + timing ranking','limits':['全部匹配均为候选，未确认同用途可替换','道具生效位置来自事件；火为首次起火点，闪为爆炸点','仅显示生效标记，未恢复真实烟雾体素、火焰覆盖或闪光强度','轨迹每 4 tick 采样，人物每 8 tick 采样；出手 tick 为首次可见弹体，非原始按键','64 tick/s，115 秒回合时间假设','坐标变换使用已提取的本地静态地图；动态门和可破坏物未回放','原站坐标按钮未返回可用剪贴板内容，未把未知坐标补成事实']}
 (D/'teaching.json').write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({k:out[k] for k in ['demo_count','observed_throw_count']},ensure_ascii=False));print(json.dumps([{k:t[k] for k in ['name','total_candidates','status']} for t in lessons],ensure_ascii=False))
if __name__=='__main__':main()
