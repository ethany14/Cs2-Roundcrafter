"""Bounded player-information evidence, separate from retrospective spectator facts."""
import argparse
import hashlib
import json
from collections import Counter
from .casebook import ROOT,connect,get_case
from .geometry import Mesh,sight


def algorithm_hash():
    from pathlib import Path
    files=[Path(__file__),Path(__file__).parent/'geometry.py',Path(__file__).parent/'smoke.py',Path(__file__).parent/'smoke_voxels.py',Path(__file__).parent/'damage_evidence.py',Path(__file__).parent/'map_assets.py',Path(__file__).parent/'solid_geometry.py']
    solids_metadata=ROOT/'data/maps/convex-solids.json'
    if solids_metadata.exists():files.append(solids_metadata)
    metadata=ROOT/'data/maps/current-scene.json'
    voxel_db=ROOT/'data/maps/smoke-frames.sqlite'
    voxel_version=str((voxel_db.stat().st_size,voxel_db.stat().st_mtime_ns)) if voxel_db.exists() else 'absent'
    damage_version=str([(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted((ROOT/'data/casebook').glob('*-damage.json'))])
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)+(metadata.read_bytes() if metadata.exists() else b'')+voxel_version.encode()+damage_version.encode()).hexdigest()


def reconstruct(case,mesh):
    evidence=case['evidence'];tick=case['tick'];actor_id=case['actor']
    from .smoke_voxels import frames_for_case
    from .damage_evidence import for_case as damage_for_case
    smokes=frames_for_case(case)
    history=[h for h in evidence.get('history',[]) if h['tick']<=tick]
    current=next(p for p in evidence['snapshot'] if p['player']==actor_id)
    spotted=[];last={};geometry=[]
    for frame in history:
        actor=next((p for p in frame['players'] if p['player']==actor_id and p['alive']),None)
        if actor is None:continue
        friends={p['player'] for p in frame['players'] if p['side']==case['side'] and p['alive']}
        for enemy in frame['players']:
            if enemy['side']==case['side'] or not enemy['alive']:continue
            by=enemy.get('approximate_spotted_by')
            if by is not None and friends.intersection(by):
                item={'enemy':enemy['player'],'tick':frame['tick'],'reported_position':enemy['position'],
                      'source':'parser_approximate_spotted_by_self' if actor_id in by else 'parser_approximate_spotted_by_teammate',
                      'certainty':'approximate engine flag; not confirmed perception or voice communication'}
                spotted.append(item);last[enemy['player']]=item
            if frame['tick']==tick:
                geometry.append({'enemy':enemy['player'],**sight(mesh,actor,enemy,smokes,tick,case['tick_rate'],evidence.get('smoke_disturbances'))})
    # Support geometry uses actual enemy positions: keep exclusively in spectator diagnostics.
    support=[]
    for teammate in evidence['snapshot']:
        if teammate['side']!=case['side'] or not teammate['alive'] or teammate['player']==actor_id:continue
        for enemy in evidence['snapshot']:
            if enemy['side']==case['side'] or not enemy['alive']:continue
            support.append({'teammate':teammate['player'],'enemy':enemy['player'],**sight(mesh,teammate,enemy,smokes,tick,case['tick_rate'],evidence.get('smoke_disturbances'))})
    return {'schema':1,'algorithm_sha256':algorithm_hash(),'case_id':case['id'],'as_of_tick':tick,
      'player_information':{'self':{k:v for k,v in current.items() if k!='approximate_spotted_by'},'team_alive':case['features']['own_alive'],
          'movement_context':{'move_type':current.get('move_type'),'on_ladder':current.get('move_type')==9 if current.get('move_type') is not None else None,
                              'ladder_surface_index':current.get('ladder_surface_index'),
                              'basis':'CS2 network MoveType 9; ladder surface index alone does not establish current ladder contact'},
          'recent_spotting_evidence':spotted,'last_reported_enemies':[dict(v,age_seconds=(tick-v['tick'])/case['tick_rate']) for v in last.values()],
          'sound_information':'unavailable: no audible-radius or occlusion reconstruction',
          'voice_information':'unavailable','history_seconds':5,'sampling_seconds':0.5,
          'limits':'No spotting flag does NOT mean player did not know. Enemy HP/equipment omitted; flags do not establish conscious perception.'},
      'spectator_geometry':{'actor_to_enemies':geometry,'teammates_to_enemies':support,
          'use':'Only verify conditional lines of sight; never treat these enemy positions as player-known.'},
      'retrospective_shot_evidence':{'events':[e for e in evidence.get('events',[]) if e.get('through_smoke') or (e.get('penetrated_surfaces') or 0)>0],
                                   'use':'Observed death-event flags; may occur AFTER query tick. Never use to reconstruct earlier player information.'},
      'retrospective_damage_evidence':damage_for_case(case),
      'geometry_provenance':{'mesh_sha256':mesh.sha256,'source':getattr(mesh,'asset_provenance',{}).get('source','legacy OBJ'),
          'map_policy':'Use current installed map for recent matches as requested; no exact historical version claim',
          'map_version_verified':False,'method':'independent BVH on local collision materials; separate static door render mesh',
          'limits':['Dynamic door transforms not reconstructed; current Dust2 entity export contains no discovered dynamic door/ladder classes',
                    'Material identifies surface, not exact transparency or weapon damage',
                    'Network smoke occupancy available only where frames imported; grid mapping/interior fill inferred, rendered opacity unavailable','No navigation, reaction time, weapon readiness or actual trade feasibility']},
      'decision_gate':{'can_score_decision':False,'allowed':'Evidence-based conditional hypotheses and explicit uncertainty',
          'missing':['actual visibility validation','complete player information','team intent and feasible alternatives','ballistic and dynamic-state validation']}}


def inspect(db,identifier):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='perception'").fetchone():
        return {'status':'not_enriched','case_id':identifier}
    row=db.execute('SELECT payload,case_sha FROM perception WHERE id=?',(identifier,)).fetchone()
    if not row:return {'status':'not_enriched','case_id':identifier}
    case=get_case(db,identifier)
    if row['case_sha']!=hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest():
        return {'status':'stale_rebuild_required','case_id':identifier}
    result=json.loads(row['payload'])
    if result.get('algorithm_sha256')!=algorithm_hash():return {'status':'stale_rebuild_required','case_id':identifier}
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0);args=p.parse_args()
    from .map_assets import load_scene
    mesh=load_scene()
    totals=Counter()
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS perception(id TEXT PRIMARY KEY,case_sha TEXT,payload TEXT)')
        rows=db.execute('SELECT id,payload FROM cases ORDER BY id').fetchall()
        if args.limit:rows=rows[:args.limit]
        for index,row in enumerate(rows):
            case=json.loads(row['payload']);result=reconstruct(case,mesh)
            db.execute('INSERT OR REPLACE INTO perception VALUES(?,?,?)',(case['id'],hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest(),json.dumps(result)))
            totals['cases']+=1;totals['cases_with_spotting']+=bool(result['player_information']['recent_spotting_evidence'])
            for pair in result['spectator_geometry']['actor_to_enemies']:
                totals['actor_enemy_rays']+=1;totals['blocked']+=not pair['static_ray_clear'];totals['smoke_overlap']+=pair['smoke_overlap_possible']
                totals['disturbed_smoke_rays']+=pair['smoke_analysis']['status']=='disturbed_opacity_unknown'
                totals['static_doorway_crossing_rays']+=bool(pair['static_doorway_models_crossed'])
                for hit in pair['line_of_fire']['head_ray_crossings']:totals['surface_'+hit['material']]+=1
            totals['actor_on_ladder']+=result['player_information']['movement_context']['on_ladder'] is True
            if index%100==0:db.commit();print(f'Enriched {index+1}/{len(rows)}',flush=True)
    out=ROOT/'outputs/casebook';out.mkdir(parents=True,exist_ok=True)
    (out/'perception-validation.json').write_text(json.dumps({'counts':dict(totals),'map_version_verified':False,'decision_quality_validated':False,'mesh_sha256':mesh.sha256},indent=2),encoding='utf-8')
    print(json.dumps(dict(totals)))

if __name__=='__main__':main()
