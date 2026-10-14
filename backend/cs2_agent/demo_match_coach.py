"""Explicitly authorized, bounded match analysis using the existing Eregion coach."""
import json,re,threading,time
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from urllib.parse import urlsplit
from . import demo_coach as coach, demo_review as dr
from .lineup_catalog import write_json
from .provider import load_config

ACTIVE={}
MAX_SECONDS=1800
PER_ROUND_CALLS=2

def launch(target,args):threading.Thread(target=target,args=args,daemon=True,name="demo-match-coach").start()

def destination():
    try:return {'host':urlsplit(load_config()['endpoint']).hostname,'configured':True}
    except ValueError:return {'host':None,'configured':False}

def job_path(mid,jid):
    if not isinstance(jid,str) or not re.fullmatch('[0-9a-f]{32}',jid):raise ValueError('无效任务编号')
    return dr.folder(mid)/'analysis-jobs'/(jid+'.json')

def index(mid):
    result=dr.result(mid);rounds=[];claims=[]
    for row in result['rounds']:
        n=row['number'];p=coach.path(mid,n)
        s=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
        status=s.get('status','not_analyzed')
        if status=='running' and (mid,n) not in coach.ACTIVE:status='interrupted'
        report=s.get('result') or s.get('previous_result')
        rounds.append({'round':n,'status':status,'version':s.get('version'), 'model_calls':s.get('model_calls',0),'has_result':bool(report)})
        if report:
            for i,c in enumerate(report['claims']):claims.append({'id':f'{n}:{i}','round':n,'title':c['observed_title'],'side':c.get('side','T'),'start':c['start'],'end':c['end'],'players':c['players'],'previous':not bool(s.get('result'))})
    jobs=[]
    for p in (dr.folder(mid)/'analysis-jobs').glob('*.json'):
        j=json.loads(p.read_text(encoding='utf-8'))
        if j['status']=='running' and mid not in ACTIVE:j['status']='interrupted'
        live=sum(max(0,active.state.get('model_calls',active.used)-active.used) for n in j.get('current_rounds',[j.get('current_round')]) if (active:=coach.ACTIVE.get((mid,n))) is not None)
        if live:j={**j,'calls':j['calls']+live}
        jobs.append(j)
    return {'destination':destination(),'rounds':rounds,'claims':claims,'job':max(jobs,key=lambda j:j['created_at']) if jobs else None,'supported':result['map'] in ('de_nuke','de_dust2')}

def start(raw):
    mid=raw['match'];jid=raw['request_id'];p=job_path(mid,jid)
    if p.exists():return json.loads(p.read_text(encoding='utf-8'))
    dest=destination()
    if raw.get('consent') is not True or not dest['configured'] or raw.get('endpoint_host')!=dest['host']:raise ValueError('请核对模型目的地并明确授权匿名比赛证据发送')
    data=dr.result(mid)
    if data['map'] not in ('de_nuke','de_dust2'):raise ValueError('目前战术解释支持 Nuke 与 Dust2')
    ns=raw.get('rounds',[r['number'] for r in data['rounds']])
    valid={r['number'] for r in data['rounds']}
    if not isinstance(ns,list) or not ns or any(type(n) is not int or n not in valid for n in ns) or len(set(ns))!=len(ns):raise ValueError('无效回合范围')
    budget=raw.get('max_calls')
    if type(budget) is not int or not 1<=budget<=200:raise ValueError('整批新增调用预算须为1至200')
    lang='en' if raw.get('lang')=='en' else 'zh'
    concurrency=raw.get('concurrency',3)
    if type(concurrency) is not int or not 1<=concurrency<=4:raise ValueError('同时分析回合数须为1至4')
    if not coach.LOCK.acquire(False):raise RuntimeError('已有分析正在运行，请等待或取消')
    try:
        # Completed current-version results are reusable; regeneration must be deliberate.
        if raw.get('regenerate') is not True:
            ns=[n for n in ns if not (coach.path(mid,n).exists() and (s:=json.loads(coach.path(mid,n).read_text(encoding='utf-8'))).get('status')=='completed' and s.get('version')==coach.VERSION and s.get('lang','zh')==lang)]
        job={'id':jid,'match':mid,'created_at':time.time(),'status':'running','rounds':ns,'completed':[],'failed':[],'current_round':None,'calls':0,'max_calls':budget,'endpoint_host':dest['host'],'lang':lang,'per_round_max':PER_ROUND_CALLS,'max_seconds':MAX_SECONDS,'concurrency':concurrency,'current_rounds':[],'reserved_calls':0}
        write_json(p,job);event=threading.Event();ACTIVE[mid]=(job,event)
    except Exception:coach.LOCK.release();raise
    launch(run,(job,event,p))
    return job

def run(job,event,p):
    mid=job['match'];started=time.monotonic();pending={};todo=iter(job['rounds']);exhausted=False
    def analyze(n,allowance):
        s=None
        try:
            if event.is_set():return n,0,'cancelled',None
            s=coach.Session(mid,n,additional_calls=allowance,endpoint_host=job['endpoint_host']);s.lang=job.get('lang','zh');getattr(s,'state',{})['lang']=s.lang
            s.cancelled=event;s.deadline=started+MAX_SECONDS;coach.ACTIVE[mid,n]=s;s.run()
            return n,s.state['model_calls']-s.used,s.state['status'],None
        except Exception as exc:
            return n,max(0,s.state.get('model_calls',s.used)-s.used) if s else 0,'failed',type(exc).__name__
        finally:coach.ACTIVE.pop((mid,n),None)
    def persist():
        job['current_rounds']=sorted(n for n,_ in pending.values())
        job['current_round']=job['current_rounds'][0] if job['current_rounds'] else None
        job['reserved_calls']=sum(allowance for _,allowance in pending.values())
        write_json(p,job)
    try:
        with ThreadPoolExecutor(max_workers=job.get('concurrency',3),thread_name_prefix='demo-round') as pool:
            while True:
                expired=time.monotonic()-started>=MAX_SECONDS
                if expired:event.set();job['budget_reason']='time_budget'
                while not event.is_set() and not exhausted and len(pending)<job.get('concurrency',3):
                    available=job['max_calls']-job['calls']-sum(a for _,a in pending.values())
                    if available<=0:break
                    try:n=next(todo)
                    except StopIteration:exhausted=True;break
                    allowance=min(PER_ROUND_CALLS,available)
                    # Only the coordinator writes the job; all in-flight allowances are reserved.
                    future=pool.submit(analyze,n,allowance);pending[future]=(n,allowance);persist()
                if not pending:break
                done,_=wait(pending,timeout=.2,return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future);n,calls,status,reason=future.result();job['calls']+=calls
                    if status=='completed':job['completed'].append(n)
                    else:job['failed'].append({'round':n,'status':status,**({'reason':reason} if reason else {})})
                if done:persist()
        if job.get('budget_reason')=='time_budget':job['status']='budget_exhausted'
        elif event.is_set():job['status']='cancelled'
        elif len(job['completed'])+len(job['failed'])<len(job['rounds']):job.update(status='budget_exhausted',budget_reason='call_budget')
        else:job['status']='completed_with_failures' if job['failed'] else 'completed'
    except Exception as exc:job.update(status='failed',failure_type=type(exc).__name__)
    finally:
        job['completed'].sort();job['failed'].sort(key=lambda x:x['round'])
        job.update(current_round=None,current_rounds=[],reserved_calls=0,elapsed_seconds=round(time.monotonic()-started,2))
        write_json(p,job);ACTIVE.pop(mid,None);coach.LOCK.release()

def cancel(raw):
    current=ACTIVE.get(raw['match'])
    if current:current[1].set()
    return {'cancel_requested':bool(current)}
