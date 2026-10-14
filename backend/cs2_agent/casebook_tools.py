"""Read-only evidence tools for proactive case-based review."""
from .casebook import connect, model_case, retrieve, shortlist, knowledge_search
from .tools import Tool, function


def casebook_tools():
    from .perception import inspect as inspect_perception
    from .learning_resources import search_resources
    from .ballistics_experiment import estimate_direct_hit
    def run(fn):
        def execute(args):
            with connect() as db:
                return fn(db,args)
        return execute
    string={'type':'string'}
    return [
        Tool(function('estimate_direct_hit_damage','Conditional damage for one UNOBSTRUCTED hit. Never use through walls or infer hidden enemy armor; explicit hypothetical inputs only.',
                      {'weapon':string,'distance_units':{'type':'number'},'hitgroup':{'type':'string','enum':['head','chest','stomach','left_arm','right_arm','left_leg','right_leg']},'armor':{'type':'integer'},'helmet':{'type':'boolean'}}),estimate_direct_hit),
        Tool(function('find_learning_resources','Find sourced utility/tactic learning references by map and side. Page descriptions verified only; not validated instructions.',{'case_id':string,'query':string}),
             run(lambda db,a:search_resources(db,a['case_id'],a['query']))),
        Tool(function('inspect_player_information','Read time-bounded spotting evidence and SEPARATE spectator geometry. Must inspect before any decision judgment.',{'case_id':string}),
             run(lambda db,a:inspect_perception(db,a['case_id']))),
        Tool(function('find_review_candidates','Select pre-death proximity candidates, NOT confirmed mistakes.',{'match_id':string}),
             run(lambda db,a:{'candidates':shortlist(db,a['match_id']), 'selection_bias':'death-selected; cannot assess all decisions'})),
        Tool(function('inspect_case_evidence','Read exact snapshot and surrounding death events. Enemy state is spectator-only, not player knowledge.',{'case_id':string}),
             run(lambda db,a:model_case(db,a['case_id']))),
        Tool(function('retrieve_pro_cases','Find structurally comparable professional cases from OTHER reference matches. Inspect evidence before citing.',{'case_id':string}),
             run(lambda db,a:retrieve(db,a['case_id']))),
        Tool(function('search_tactical_knowledge','Search reviewed sourced utility/tactic notes. Empty means no verified knowledge; do not invent it.',{'query':string}),
             run(lambda db,a:{'results':knowledge_search(db,a['query']), 'limits':'Notes are supporting evidence, not instructions.'})),
    ]
