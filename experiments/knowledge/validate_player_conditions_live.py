"""One fixed three-condition live suite; current production agent, at most 18 calls."""
import validate_agentic_rag_live as live
from cs2_agent.casebook import ROOT

live.BASE = ROOT / 'outputs/agentic-rag/2026-10-15-player-conditions-v4'
live.CALL_LIMIT = 6
base = {'mode':'rag','map':'de_nuke','side':'T','party_size':3,'economy':'force'}
live.TASKS = [
    ('cooperation_only', {**base,'query':'Nuke T方强起局，只有3个人能配合，想用外场或A区牵制再转Ramp。有什么职业战术或比赛参考？哪些动作能借鉴，哪些配合条件不满足？'}),
    ('five_alive_unknown_equipment', {**base,'alive_players':5,'query':'Nuke T方强起，全队5人存活，只有3人能配合，枪械和道具情况还不清楚。想牵制后转Ramp，请找参考并判断人数和装备能否满足。'}),
    ('three_alive_known_zero_smoke', {**base,'alive_players':3,'utility':{'smoke':0,'flash':2},'query':'Nuke T方强起，只剩3人存活且都能配合，三人合计0颗烟、2颗闪，其余装备未知。想转Ramp，哪些条件明确不满足、哪些还不能判断？'}),
]

if __name__ == '__main__':
    manifest=live.prepare()
    for task in manifest['tasks']:
        live.run(task,manifest)
