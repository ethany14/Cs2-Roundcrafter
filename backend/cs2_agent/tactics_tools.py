from .tools import Tool,function
from .tactics_rag import retrieve
from .nuke_teaching import check,plan,teaching

def nuke_tools():
 from .tactical_solver import latest,check_latest
 return [Tool(function('inspect_tactical_solver','Read source-grounded tactical constraints and independently simulated candidates; no certified lineups.',{}),lambda args:latest()),Tool(function('check_tactical_solver_timing','Check a stored candidate against countdown and provided travel duration; unknown route duration stays unknown.',{'candidate_index':{'type':'integer'},'clock':{'type':'number'},'travel_seconds':{'type':'number'}},required=['candidate_index','clock']),check_latest),Tool(function('inspect_nuke_teaching','Read the Nuke pilot plan and demo candidate links. All matches require review.',{}),lambda args:{'plan':plan(),'teaching':{k:v for k,v in teaching().items() if k!='cases'},'viewer':'http://127.0.0.1:8790/nuke'}),
  Tool(function('check_nuke_execution','Check individual remaining utility, exclusive role assignment, communication and countdown ordering. No optimality or execution certification.',{'map':{'type':'string'},'side':{'type':'string'},'phase':{'type':'string'},'clock':{'type':'number'},'players':{'type':'array','items':{'type':'object'}},'completed':{'type':'array','items':{'type':'object'}},'assignment':{'type':'object'}},required=['map','side','phase','clock','players']),check)]
def tactics_tools():
 return [Tool(function('retrieve_tactic_cards','Retrieve source-verified metadata and unknown prerequisites. Learning references only; no executable recommendation or win-rate claim.',{'map':{'type':'string'},'side':{'type':'string','enum':['T','CT']},'economy':{'type':'string','enum':['pistol','rifle','eco','force','unknown']},'query':{'type':'string','maxLength':300},'players':{'type':'integer','minimum':1,'maximum':5},'party_size':{'type':'integer','minimum':1,'maximum':5}},required=['map','side','economy']),retrieve)]
