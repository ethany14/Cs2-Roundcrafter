from .tools import Tool,function
from .strategy import inspect_sample,DIRECTORY
def strategy_tools():
 def execute(args):
  if not (DIRECTORY/'metrics.json').exists():return {'status':'not_trained'}
  return inspect_sample(args['sample_index'])
 return [Tool(function('inspect_postplant_strategy','Inspect a registered known-bomb-position scenario and conditional retake/regroup/save candidates. Behaviour probabilities are not optimal-action scores.',{'sample_index':{'type':'integer','minimum':0}}),execute)]
