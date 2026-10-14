"""Replay actual professional continuations as sourced overlays, never as optimal labels."""
import json
import subprocess
from .casebook import ROOT,connect,get_case
from .studio import DIRECTORY

def build():
    manifest=json.loads((ROOT/'data/situation/manifest.json').read_text())['demos']
    clips=json.loads((DIRECTORY/'index.json').read_text());groups={}
    with connect() as db:
        for row in clips:
            k=json.loads((DIRECTORY/(row['id']+'-planning.json')).read_text(encoding='utf-8'))
            for ref in k['reference_cases']:
                c=get_case(db,ref['id']);groups.setdefault(c['match_id'],{})[c['id']]=c
    trajectories={}
    for match,cases in groups.items():
        entry=next(d for d in manifest if d['match_id']==match)
        input_path=DIRECTORY/(match+'-reference-input.json');output_path=DIRECTORY/(match+'-reference-private.json')
        input_path.write_text(json.dumps(list(cases.values())))
        subprocess.run(['node',str(ROOT/'experiments/studio_frames.cjs'),str((ROOT/'data/situation'/entry['path']).resolve()),str(input_path),str(output_path)],check=True,cwd=ROOT)
        frames=json.loads(output_path.read_text())
        for identifier,c in cases.items():
            samples=[]
            for f in frames[identifier]:
                p=next(p for p in f['players'] if p['player']==c['actor'])
                if not p['alive']:break
                samples.append({'time':f['time'],'position':p['position']})
            trajectories[identifier]={'id':identifier,'source':c['source_url'],'round':c['round'],'samples':samples,'limits':'Actual professional continuation, original map coordinates; not aligned, predicted or optimal.'}
    for row in clips:
        path=DIRECTORY/(row['id']+'.json');payload=json.loads(path.read_text(encoding='utf-8'))
        payload['professional_paths']=[trajectories[r['id']] for r in payload['knowledge']['reference_cases'] if r['id'] in trajectories]
        path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'professional_paths':len(trajectories),'clips':len(clips)}))

if __name__=='__main__':build()
