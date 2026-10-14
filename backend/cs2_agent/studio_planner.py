"""Bounded counterfactual plans via the existing Eregion AgentLoop."""
import json
import hashlib
import re
from uuid import uuid4
from urllib.parse import urlsplit
from .casebook import ROOT,connect,get_case
from .studio import DIRECTORY,visible_players
from .host import WorkspaceHost
from .provider import ConfiguredModel
from .tools import Tool,function

BRANCHES=('continue','cooperate','counter')


def evidence_hash(packet):
    return hashlib.sha256(json.dumps(packet,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def cached_plans(identifier):
    path=DIRECTORY/(identifier+'-plans.json')
    if not path.exists():return None
    try:
        result=json.loads(path.read_text(encoding='utf-8'));packet=planning_packet(identifier)
        if result.get('evidence_hash')!=evidence_hash(packet):return None
        result['plans']=validate_plans(result['plans'],packet['knowledge'])
        return result
    except (ValueError,KeyError,TypeError):return None


def validate_plans(plans,knowledge):
    if not isinstance(plans,list) or not 2<=len(plans)<=3:raise ValueError('Need two or three plans')
    routes={r['id']:r for r in knowledge['routes']};seen=set();result=[]
    for index,p in enumerate(plans):
        rid=p['route_id']
        if rid not in routes or rid in seen:raise ValueError('Unknown or duplicated route')
        seen.add(rid)
        def text(value):
            if not isinstance(value,str) or not value.strip() or len(value)>700:raise ValueError('Invalid explanation')
            return value
        responses={}
        for branch in BRANCHES:
            actors=[];used=set()
            for actor in p.get('responses',{}).get(branch,[]):
                player=actor['player'];route=actor['route_id']
                # A redundant copy of the focal actor's already selected route is not another actor response.
                if player==knowledge.get('actor') and route==rid:continue
                if player in used or player not in knowledge['other_actor_routes']:raise ValueError('Unknown or duplicated actor')
                if route not in {r['id'] for r in knowledge['other_actor_routes'][player]}:raise ValueError('Unknown actor route')
                used.add(player);actors.append({'player':player,'route_id':route})
            responses[branch]=actors
        risks=p['risks'];assumptions=p['assumptions']
        stated=re.match(r'\s*(\d+)[vV](\d+)',p.get('reason',''))
        if stated and knowledge.get('alive') and tuple(map(int,stated.groups()))!=(knowledge['alive']['own'],knowledge['alive']['enemy']):
            raise ValueError('Reason starts with incorrect alive counts; use the supplied alive state')
        if not isinstance(risks,list) or not 1<=len(risks)<=4 or not isinstance(assumptions,list) or not 1<=len(assumptions)<=4:raise ValueError('Risks and assumptions required')
        if knowledge.get('objective'):
            for field in ('objective','trigger','abort_condition'):text(p.get(field))
            if any(p['objective']==q.get('objective') for q in result):raise ValueError('Plans must have different tactical objectives')
        result.append({'objective':p.get('objective',''),'trigger':p.get('trigger',''),'abort_condition':p.get('abort_condition',''),'id':f'ai-{index}','route_id':rid,'title':text(p['title']),'reason':text(p['reason']),
                       'risks':[text(s) for s in risks],'assumptions':[text(s) for s in assumptions],
                       'responses':responses,'response_notes':{b:text(p['response_notes'][b]) for b in BRANCHES}})
    return result


def planning_packet(identifier):
    knowledge=json.loads((DIRECTORY/(identifier+'-planning.json')).read_text(encoding='utf-8'))
    references=[]
    with connect() as db:
        for ref in knowledge['reference_cases']:
            c=get_case(db,ref['id'])
            actor=next(p for p in c['evidence']['snapshot'] if p['player']==c['actor'])
            references.append({'id':ref['id'],'map':c['map'],'side':c['side'],'round':c['round'],'tick':c['tick'],
                               'own_position':actor['position'],'own_yaw':actor['yaw'],
                               'own_recent_path':[next(p['position'] for p in f['players'] if p['player']==c['actor']) for f in c['evidence']['history']],
                               'source':c['source_url'],'limits':'Professional example is not an optimality label; this is the past path, not a future recommendation.'})
    return {'knowledge':knowledge,'references':references}


class PlanningHost(WorkspaceHost):
    def __init__(self,directory,model,packet,max_calls=5):
        self.packet=packet;self.read=False;self.references_read=False;self.plans=None
        string={'type':'string'};actor={'type':'object','properties':{'player':string,'route_id':string},'required':['player','route_id'],'additionalProperties':False}
        schema={'type':'array','minItems':2,'maxItems':3,'items':{'type':'object','properties':{
            'route_id':string,'title':string,'reason':string,'risks':{'type':'array','items':string},'assumptions':{'type':'array','items':string},
            'responses':{'type':'object','properties':{b:{'type':'array','items':actor} for b in BRANCHES},'required':list(BRANCHES)},
            'objective':string,'trigger':string,'abort_condition':string,'response_notes':{'type':'object','properties':{b:string for b in BRANCHES},'required':list(BRANCHES)}},
            'required':['route_id','title','reason','risks','assumptions','responses','response_notes','objective','trigger','abort_condition'],'additionalProperties':False}}
        tools=[Tool(function('read_decision_context','Read only decision-time known information, available paths and response candidates.',{}),lambda a:self.read_context()),
               Tool(function('read_professional_references','Read bounded past professional examples; no future outcomes.',{}),lambda a:self.read_references()),
               Tool(function('submit_decision_plans','Submit 2-3 conditional plans using ONLY the supplied route IDs; no arbitrary positions.',{'plans':schema}),lambda a:self.submit(a['plans']))]
        request=('为这个 CS2 片段生成 2–3 个可在 3D 中比较的操作方案。先读取局势与职业参考，再提交方案并 finish_task。'
                 '不要机械输出站住/退回/横移。比较实质不同的战术目标，默认只推荐两个，第三个必须有独立价值。每项给出 objective 战术目的、trigger 执行条件、abort_condition 放弃条件。自身存活数为1时没有活队友可等待。读取 own_loadout 和 bomb_age，说明时间压力与道具限制。不要给地图坐标猜测未提供的具体地名；几何射线遮挡数量不是对敌安全性。动作只展示首个6秒决策窗口，后续依据信息重评，不是假定35秒都不变。没有可比较职业参考时如实说明。'
                 '只可选择给定路线，不得编造坐标、隐藏敌人位置、击杀或胜率。候选路线不代表好决策，地图检查只是粗筛。'
                 '其他玩家也要推演：continue 延续观察行为；cooperate 队友积极协同；counter 对手主动反制。'
                 '可在 responses 中为已知玩家选择提供的动作；缺失玩家会保持初始位置。敌方未被发现时，不得捏造精确站位。'
                 '解释各分支下的收益、风险与假设。最可能/最优只是待验证策略假设，不能作确定结论。职业参考是过去行为，不是最佳打法标签。用中文简洁回答。')
        super().__init__(directory,model,tools,request=request,max_calls=max_calls)

    def read_context(self):self.read=True;return self.packet['knowledge']
    def read_references(self):self.references_read=True;return self.packet['references']
    def submit(self,plans):
        if not self.read or not self.references_read:return {'accepted':False,'next':'Call read_decision_context and read_professional_references before submitting.'}
        try:self.plans=validate_plans(plans,self.packet['knowledge'])
        except (ValueError,KeyError,TypeError) as e:return {'accepted':False,'next':str(e)}
        return {'accepted':True,'plans':len(self.plans)}
    def execute(self,call,turn):
        if call['name']=='finish_task' and self.plans is None:return {'finished':False,'next':'Submit validated plans first'}
        return super().execute(call,turn)


def generate(identifier,progress=lambda s:None):
    packet=planning_packet(identifier);job_id=uuid4().hex;model=ConfiguredModel();host=None
    destination=urlsplit(model.config['endpoint']).hostname
    output=ROOT/'outputs/studio';output.mkdir(exist_ok=True,parents=True)
    (output/(job_id+'-sent-evidence.json')).write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        progress('Agent 正在读取局势、比较参考与响应分支')
        host=PlanningHost(ROOT/'data/core-tasks'/job_id,model,packet)
        status=host.run(slice_steps=80)
        if host.plans is None or host.state['status']!='completed':raise RuntimeError('模型未在调用预算内完成有效方案')
        result={'case_id':identifier,'source':'ai_hypotheses','plans':host.plans,'calls':host.state['calls'],'job_id':job_id,'destination':destination,'evidence_hash':evidence_hash(packet)}
        (DIRECTORY/(identifier+'-plans.json')).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        lines=['# 3D 决策推演报告','',f'案例：{identifier}。本次模型调用 {host.state["calls"]} 次。','',
               '这是候选操作与其他玩家响应的条件性推演，不是已验证的更优解。没有使用目标片段的实际未来或未发现敌人的坐标。','']
        for p in host.plans:
            lines += ['## '+p['title'],'',p['reason'],'','假设：'+'；'.join(p['assumptions']),'','风险：'+'；'.join(p['risks']),'']
            for b in BRANCHES:lines += ['- '+b+'：'+p['response_notes'][b]]
        (output/(job_id+'.md')).write_text('\n'.join(lines),encoding='utf-8')
        return result
    finally:
        if host:host.close()
        model.close()
