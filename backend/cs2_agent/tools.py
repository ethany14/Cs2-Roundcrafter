"""Domain tools plug in here; the kernel owns the execution loop."""
from dataclasses import dataclass
from typing import Callable


def function(name, description, properties, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties,
                       "required": list(properties) if required is None else required,
                       "additionalProperties": False},
    }}


@dataclass(frozen=True)
class Tool:
    definition: dict
    execute: Callable[[dict], dict]

    @property
    def name(self):
        return self.definition["function"]["name"]


def foundation_tools():
    from .situation_tools import situation_tools
    from .temporal_tools import temporal_tools
    from .casebook_tools import casebook_tools
    from .environment_tools import environment_tools
    from .strategy_tools import strategy_tools
    from .tactics_tools import tactics_tools,nuke_tools
    return [Tool(function("inspect_capabilities", "Inspect what this CS2 workspace can actually do.", {}),
                 lambda args: {"kernel": "Eregion AgentLoop", "situation_model": "offline pilot; use inspect_situation_experiment for actual validation status",
                               "pro_demo_training": "check experiment status; no tactical understanding claim", "demo_parser": "offline situation dataset builder",
                               "next_extension": "Local professional case retrieval available; cases require human validation"})] + situation_tools() + temporal_tools() + casebook_tools() + environment_tools() + strategy_tools() + tactics_tools() + nuke_tools() + lineup_job_tools() + demo_review_tools()


def lineup_job_tools():
    from .lineup_research import start_job, get_job, cancel_job
    return [Tool(function('start_lineup_research','Run an evidence-grounded utility research task through Eregion AgentLoop; shared bounded web/video tools, not physics solving.',{
        'query':{'type':'string','minLength':1,'maxLength':300},'mode':{'type':'string','enum':['single','tactic']},
        'map':{'type':'string'},'party_size':{'type':'integer','minimum':1,'maximum':5}},required=['query','mode']),start_job),
        Tool(function('get_lineup_research','Read task progress, structured evidence, compatibility and call usage.',{'id':{'type':'string'}}),lambda args:get_job(args['id'])),
        Tool(function('cancel_lineup_research','Cancel further research calls and discard late model results.',{'id':{'type':'string'}}),lambda args:cancel_job(args['id']))]


def demo_review_tools():
    from .demo_review import library,result
    def inspect(args):
        r=result(args['id'])
        return {'map':r['map'],'analysis':r['analysis'],'limitations':r['limitations'],'tactics':[c for c in r['tactics'] if c['round']==args['round']]}
    return [Tool(function('list_demo_matches','List locally imported demo analysis jobs; no external uploads.',{}),lambda args:{'matches':library()}),
            Tool(function('inspect_demo_tactics','Read observed facts, explicit rule inferences and unknowns for a demo round. Candidates do not establish tactical intent.',{'id':{'type':'string'},'round':{'type':'integer','minimum':1,'maximum':100}}),inspect)]
