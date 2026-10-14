"""Offline damage hypotheses tested against demo events, not authoritative CS2 simulation."""
import json
import math
import re
from collections import Counter
import numpy as np
from .casebook import ROOT
from .solid_geometry import Solids


def surface_parameters():
    directory=ROOT/'data/maps';physics={};explicit={}
    for block in re.findall(r'^\t\t\{\n(.*?)^\t\t\}',(directory/'current-surfaces').read_text(),re.M|re.S):
        name=re.search(r'surfacePropertyName = "([^"]+)"',block)
        h=re.search(r'm_nameHash = (\d+)',block);base=re.search(r'm_baseNameHash = (\d+)',block)
        if name and h:physics[name[1].lower()]={'hash':int(h[1]),'base':int(base[1]) if base else None}
    for block in re.findall(r'^\t\t\{\n(.*?)^\t\t\}',(directory/'surfaceproperties_game.txt').read_text(),re.M|re.S):
        name=re.search(r'surfacePropertyName = "([^"]+)"',block)
        if not name:continue
        explicit[name[1].lower()]={k:float(v) for k,v in re.findall(r'(bulletPenetration\w+) = ([\d.]+)',block)}
    hashes={v['hash']:k for k,v in physics.items()}
    def resolve(name,visited=()):
        if name in visited:raise ValueError('Surface inheritance cycle')
        parent=hashes.get(physics.get(name,{}).get('base'))
        inherited=resolve(parent,visited+(name,)) if parent else {}
        return {**inherited,**explicit.get(name,{})}
    return {name:{'resolved':resolve(name),'explicit':explicit.get(name,{}),'base':hashes.get(p['base'])} for name,p in physics.items()}


def scale_damage(raw,weapon,hitgroup,armor,helmet):
    multipliers={'head':weapon['m_flHeadshotMultiplier'],'stomach':1.25,'chest':1.,'left_arm':1.,'right_arm':1.,'left_leg':.75,'right_leg':.75}
    if hitgroup not in multipliers:raise ValueError('Unsupported hitgroup')
    damage=raw*multipliers[hitgroup]
    covered=hitgroup not in ('left_leg','right_leg') and (hitgroup!='head' or helmet)
    if armor>0 and covered:
        health=damage*min(1.,weapon['m_flArmorRatio']*.5)
        armor_cost=(damage-health)*.5
        damage=damage-armor*2 if armor_cost>armor else health
    return max(0,math.floor(damage))


def direct_damage(weapon,distance,hitgroup,armor,helmet):
    if not math.isfinite(distance) or distance<0 or distance>weapon['m_flRange']:raise ValueError('Invalid or out-of-range distance')
    raw=weapon['m_nDamage']*weapon['m_flRangeModifier']**(distance/500.)
    return scale_damage(raw,weapon,hitgroup,armor,helmet)


def estimate_direct_hit(args):
    """Conditional calculator, deliberately excludes penetration and player state inference."""
    distance=args['distance_units'];armor=args['armor'];helmet=args['helmet']
    if isinstance(distance,bool) or not isinstance(distance,(int,float)):raise ValueError('Numeric distance required')
    if isinstance(armor,bool) or not isinstance(armor,int) or not 0<=armor<=100:raise ValueError('Armor must be 0..100')
    if type(helmet) is not bool:raise ValueError('Helmet must be boolean')
    name=args['weapon'];name=name if name.startswith('weapon_') else 'weapon_'+name
    supported={'ak47','m4a1','m4a1_silencer','awp','ssg08','galilar','famas','aug','sg556','glock','hkp2000','usp_silencer','p250','tec9','fiveseven','cz75a','deagle','revolver','mp9','mac10','mp7','mp5sd','ump45','bizon','p90','negev','m249','scar20','g3sg1'}
    if name.removeprefix('weapon_') not in supported:raise ValueError('Only supported single-projectile firearms are allowed')
    weapons=json.loads((ROOT/'data/maps/weapon-ballistics.json').read_text())['weapons']
    if name not in weapons or name=='weapon_base':raise ValueError('Unsupported weapon')
    return {'status':'conditional_direct_hit_estimate','damage':direct_damage(weapons[name],distance,args['hitgroup'],armor,helmet),
            'inputs':args,'assumptions':'One hit at the stated hitgroup, armor and range, without penetrating any object; not hit probability or proof of a feasible shot.',
            'knowledge_boundary':'Armor and helmet are hypothetical inputs unless separately established as player-known.',
            'validation':'667 matched lethal nonpenetration events across six local demos: maximum observed error 1 damage; not fresh blind validation.',
            'wall_damage_supported':False}


def candidate_wall_damage(weapon,distance,hitgroup,armor,helmet,layers,parameters):
    """Legacy-style hypothesis. No claim these asset modifiers map to modern loss coefficients."""
    raw=weapon['m_nDamage']*weapon['m_flRangeModifier']**(distance/500.)
    previous=-1.
    for layer in layers:
        if layer['entry_fraction']<previous-1e-6:raise ValueError('Overlapping solids; material ownership unresolved')
        previous=layer['exit_fraction']
        if layer['segment_starts_inside'] or layer['segment_ends_inside']:raise ValueError('Incomplete solid traversal')
        if layer['collision_tags']:raise ValueError('Conditional collision semantics unresolved')
        p=parameters[layer['material']]['resolved'];modifier=p.get('bulletPenetrationDistanceModifier')
        if modifier is None or modifier<=0 or weapon['m_flPenetration']<=0:raise ValueError('Missing penetration parameter')
        # Deliberately quarantined candidate, to falsify before exposing to the agent.
        loss=raw*.16+3.75/(weapon['m_flPenetration']*modifier)+layer['thickness_units']**2/(24*modifier)
        raw=max(0,raw-loss)
    return scale_damage(raw,weapon,hitgroup,armor,helmet)


def main():
    weapons=json.loads((ROOT/'data/maps/weapon-ballistics.json').read_text())['weapons'];parameters=surface_parameters();solids=Solids()
    manifest=json.loads((ROOT/'data/situation/manifest.json').read_text());splits={r['match_id']:r['split'] for r in manifest['demos']}
    results=[];skipped=Counter()
    for path in sorted((ROOT/'data/casebook').glob('*-damage.json')):
        match=path.stem.split('-')[0]
        for event in json.loads(path.read_text())['events']:
            if event['penetrated_surfaces'] is None:continue
            name='weapon_'+event['weapon'];weapon=weapons.get(name)
            if not weapon:skipped['missing_weapon']+=1;continue
            if event['helmet_at_event'] is None:skipped['helmet_unknown']+=1;continue
            armor=event['armor_after']+event['armor_damage']
            try:baseline=direct_damage(weapon,event['foot_distance_units'],event['hitgroup'],armor,event['helmet_at_event'])
            except (ValueError,TypeError):skipped['unsupported_hit']+=1;continue
            row={'match':match,'split':splits[match],'tick':event['tick'],'weapon':event['weapon'],'hitgroup':event['hitgroup'],
                 'observed_damage':event['health_damage'],'penetrated_surfaces':event['penetrated_surfaces'],
                 'direct_baseline':baseline,'direct_error':baseline-event['health_damage']}
            if event['penetrated_surfaces']>0:
                target_height={'head':64,'stomach':36,'left_leg':18,'right_leg':18}.get(event['hitgroup'],48)
                start=np.asarray(event['attacker_position'])+[0,0,64];end=np.asarray(event['victim_position'])+[0,0,target_height]
                layers=solids.intervals(start,end);row['candidate_layers']=layers
                row['ray_assumption']='standing eye to approximate hitgroup center; actual impact and crouch not reconstructed'
                try:
                    if len(layers)!=event['penetrated_surfaces']:raise ValueError('Hull count differs from observed penetration count')
                    candidate=candidate_wall_damage(weapon,event['foot_distance_units'],event['hitgroup'],armor,event['helmet_at_event'],layers,parameters)
                    row['candidate_damage']=candidate;row['candidate_error']=candidate-event['health_damage']
                except (ValueError,KeyError) as error:row['candidate_unavailable']=str(error)
            results.append(row)
    summary={}
    for split in ('train','test'):
        for label,filter_fn,error in [('direct',lambda r:r['penetrated_surfaces']==0,'direct_error'),('penetration_candidate',lambda r:'candidate_error' in r,'candidate_error')]:
            values=[abs(r[error]) for r in results if r['split']==split and filter_fn(r)]
            summary[split+'_'+label]={'n':len(values),'mae':float(np.mean(values)) if values else None,'within_2_damage':sum(v<=2 for v in values),'max_absolute_error':max(values) if values else None}
    report={'summary':summary,'skipped':dict(skipped),'results':results,'agent_prediction_enabled':False,
            'limits':['Current installed weapon/surface assets assumed applicable','Lethal-event selected sample, not blind holdout','Direct formula is an offline hypothesis','Wall coefficient interpretation is unverified; no optimization against these labels','Approximate endpoints and convex-only coverage; counts are diagnostic, not eligibility for live prediction']}
    (ROOT/'data/maps/surface-ballistics.json').write_text(json.dumps(parameters,indent=2))
    (ROOT/'outputs/casebook/ballistics-experiment.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'summary':summary,'skipped':dict(skipped)}))


if __name__=='__main__':main()
