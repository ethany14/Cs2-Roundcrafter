"""Read registered, filtered environmental evidence; no raw omniscient frame export."""
import json
from .casebook import ROOT
from .tools import Tool,function

def environment_tools():
 directory=ROOT/'outputs/movement/environment'
 def inspect(args):
  index=args['sample_index']
  rows=json.loads((ROOT/'outputs/movement/comparison/rows.json').read_text())
  if type(index) is not int or not 0<=index<len(rows):return {'error':'Unknown sample index'}
  row=rows[index];records=json.loads((directory/(row['demo']+'.json')).read_text());record=next(r for r in records if r['index']==row['index']);schema=json.loads((directory/'feature-schema.json').read_text())
  return {'sample_index':index,'map':row['map'],'tick':row['tick'],'features':dict(zip(schema['names'],record['features'])),'evidence':record['details'],'ready_for_tactical_advice':False,'limitations':['Sound radius/curve support does not confirm hearing; bearings are geometric candidates.','Spotted history is approximate; positions never refresh from hidden enemies.','Static collision and effect envelopes do not reproduce dynamic props or rendering.','Zero with validity mask zero means unknown, not safe or harmless.','Penetration damage is unavailable.']}
 return [Tool(function('inspect_environment_sample','Inspect causal sound candidates, spotted history, static cover and active-effect evidence from a registered offline sample. Not proof of an optimal action.',{'sample_index':{'type':'integer','minimum':0}}),inspect)]
