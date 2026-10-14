"""Measured damage and installed weapon parameters; no invented wall-loss formula."""
import hashlib
import json
import re
from functools import lru_cache
from .casebook import ROOT


@lru_cache(maxsize=12)
def _read(path,version):
    return json.loads(path.read_text(encoding='utf-8'))


def for_case(case):
    match=str(case.get('match_id',''))
    if not re.fullmatch(r'\d+',match):return {'status':'unavailable','events':[]}
    path=ROOT/'data/casebook'/f'{match}-damage.json'
    if not path.exists():return {'status':'unavailable','events':[]}
    data=_read(path,path.stat().st_mtime_ns)
    if data['demo_sha256']!=case.get('demo_sha256'):return {'status':'hash_mismatch','events':[]}
    return {'status':'retrospective_observed_damage_not_prediction',
            'events':[e for e in data['events'] if case['tick']-3*case['tick_rate']<=e['tick']<=case['death_tick']+5*case['tick_rate'] and case['actor'] in (e['attacker'],e['victim'])],
            'use':'May occur AFTER query. Never use as earlier player knowledge or as counterfactual damage.',
            'limits':'Penetration label available only for unique lethal event joins; null means unknown.'}


def build_report():
    source=ROOT/'data/maps/weapons.vdata';text=source.read_text(encoding='utf-8')
    fields=('m_nDamage','m_flHeadshotMultiplier','m_flArmorRatio','m_flPenetration','m_flRange','m_flRangeModifier')
    weapons={}
    for name,block in re.findall(r'^\t(weapon_\w+) =\s*\n\t\{\n(.*?)^\t\}',text,re.M|re.S):
        if name.endswith('_prefab'):continue
        values={}
        for field in fields:
            m=re.search(r'^\t\t'+field+r' = ([\d.]+)$',block,re.M)
            if m:values[field]=float(m[1])
        if len(values)==len(fields):weapons[name]=values
    (ROOT/'data/maps/weapon-ballistics.json').write_text(json.dumps({'source':'local scripts/weapons.vdata_c','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'weapons':weapons},indent=2),encoding='utf-8')
    totals=[];hits=[]
    for path in sorted((ROOT/'data/casebook').glob('*-damage.json')):
        data=json.loads(path.read_text());events=data['events'];confirmed=[e for e in events if (e['penetrated_surfaces'] or 0)>0]
        totals.append({'match':path.stem.split('-')[0],'hurt_events':len(events),'confirmed_penetration_hits':len(confirmed),'unknown_penetration_hits':sum(e['penetrated_surfaces'] is None for e in events)})
        hits.extend({'match':path.stem.split('-')[0],**e} for e in confirmed)
    result={'matches':totals,'confirmed_penetration_damage':hits,'prediction_validated':False}
    (ROOT/'outputs/casebook/penetration-damage-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'weapons':len(weapons),'matches':totals}))


if __name__=='__main__':build_report()
