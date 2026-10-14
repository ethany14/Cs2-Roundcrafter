"""Spectator replay data; never merged into planning evidence."""
import hashlib
import json
import math
from .studio import DIRECTORY

def enrich():
    events=json.loads((DIRECTORY/'events-private.json').read_text())
    frames=json.loads((DIRECTORY/'actual-private.json').read_text())
    cases=json.loads((DIRECTORY/'selected.json').read_text())
    grenade_path=DIRECTORY/'grenades-private.json'
    grenades=json.loads(grenade_path.read_text()) if grenade_path.exists() else []
    grenades=[g for g in grenades if g.get('x') is not None and g['tick']%4==0]
    counts=[]
    for c in cases:
        path=DIRECTORY/(c['id']+'.json');payload=json.loads(path.read_text(encoding='utf-8'))
        def anon(value):return hashlib.sha256((c['demo_sha256']+str(value)).encode()).hexdigest()[:12]
        payload['spectator']=[{'time':f['time'],'players':[
            {k:p[k] for k in ('player','side','alive','position','yaw','pitch','duck_amount')} |
            {'role':'self' if p['player']==c['actor'] else 'ally' if p['side']==c['side'] else 'enemy'}
            for p in f['players']]} for f in frames[c['id']]]
        output=[]
        for e in events:
            t=(e['tick']-c['tick'])/64
            if not -22<=t<=c.get('duration',6):continue
            kind=e['event_name']
            if kind=='weapon_fire' and t<0:continue
            record={'time':t,'kind':kind,'player':anon(e.get('user_steamid',''))}
            if kind=='weapon_fire':
                weapon=e.get('weapon','')
                if any(s in weapon for s in ('knife','grenade','flashbang','molotov','incendiary','c4')):continue
                if e.get('user_X') is None:continue
                start=[e['user_X'],e['user_Y'],e['user_Z']+64]
                y=math.radians(e['user_yaw']);p=math.radians(e['user_pitch'])
                record.update(position=start,end=[start[0]+math.cos(y)*math.cos(p)*240,start[1]+math.sin(y)*math.cos(p)*240,start[2]-math.sin(p)*240],weapon=weapon,approximate=True)
            elif all(e.get(k) is not None for k in ('x','y','z')):record['position']=[e['x'],e['y'],e['z']]
            else:continue
            if kind in ('smokegrenade_detonate','inferno_startburn'):
                end_kind='smokegrenade_expired' if kind=='smokegrenade_detonate' else 'inferno_expire'
                expiry=next((x for x in events if x['event_name']==end_kind and x.get('entityid')==e.get('entityid') and x['tick']>e['tick']),None)
                record['duration']=(expiry['tick']-e['tick'])/64 if expiry else (20 if kind=='smokegrenade_detonate' else 7)
                record['duration_source']='demo_event' if expiry else 'illustrative_fallback'
            output.append(record)
        payload['replay_events']=output
        trajectories={}
        for g in grenades:
            t=(g['tick']-c['tick'])/64
            if not -2<=t<=c.get('duration',6):continue
            key=str(g['grenade_entity_id'])
            item=trajectories.setdefault(key,{'id':key,'kind':g['grenade_type'],'player':anon(g.get('steamid','')),'samples':[]})
            item['samples'].append({'time':t,'position':[g['x'],g['y'],g['z']]})
        payload['grenade_trajectories']=list(trajectories.values())
        path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        counts.append({'round':c['round'],'events':len(output)})
    print(json.dumps(counts))

if __name__=='__main__':enrich()
