import json,secrets,threading
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from socketserver import TCPServer
from .casebook import ROOT
from .tactics_rag import retrieve,packet,generate,build_index
PORT=8790;TOKEN=secrets.token_hex(24);LOCK=threading.Lock()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,code,data,kind='application/json; charset=utf-8'):
  b=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
 def permitted(self):
  hosts={f'127.0.0.1:{PORT}',f'localhost:{PORT}'}
  return self.headers.get('Host') in hosts and self.headers.get('Origin') in (None,*['http://'+h for h in hosts])
 def do_GET(self):
  if not self.permitted():return self.send(403,{'error':'Local only'})
  route=urlsplit(self.path).path
  if route in ('/auth/steam/start','/auth/steam/return'):
   from . import player_hub as hub
   from urllib.parse import parse_qs
   try:
    if route=='/auth/steam/start':return self.redirect(hub.openid_start())
    hub.openid_return(parse_qs(urlsplit(self.path).query));return self.redirect('/demos?view=profile&linked=1')
   except (ValueError,OSError) as e:
    from urllib.parse import quote
    return self.redirect('/demos?view=profile&link_error='+quote(str(e)[:120]))
  if route.startswith('/api/hub/') or route.startswith('/api/room/'):
   from . import player_hub as hub,tactic_room as room
   from urllib.parse import parse_qs
   q=parse_qs(urlsplit(self.path).query);one=lambda k:q.get(k,[''])[0]
   try:
    if route=='/api/hub/account':return self.send(200,hub.account())
    if route=='/api/hub/players':return self.send(200,{'players':hub.players_index()})
    if route=='/api/hub/profile':return self.send(200,hub.profile(one('steamid')))
    if route=='/api/hub/stats':
     from .player_stats import match_stats
     return self.send(200,match_stats(one('id')))
    if route=='/api/room/tactics':return self.send(200,room.listing(one('map') or None,one('q'),one('tag') or None,one('folder')))
    if route=='/api/room/tactic':return self.send(200,room.get(one('id')))
   except (ValueError,OSError,KeyError) as e:return self.send(404,{'error':str(e)[:200]})
  if route.startswith('/api/workbench/'):
   from . import demo_workbench as wb
   from urllib.parse import parse_qs
   q=parse_qs(urlsplit(self.path).query)
   try:
    if route=='/api/workbench/catalog':
     m=q.get('map',[''])[0];rows=[x for x in wb.catalog() if not m or x['map']==m]
     return self.send(200,{'matches':rows,'groups':wb.GROUPS,'reference_groups':list(wb.REFERENCE_GROUPS),'anchors':wb.ANCHORS,'maps':list(wb.MAPS),'version':wb.VERSION,
       'players':{x['id']:sorted({p for n in x['rounds'][:3] for p in wb.load_round(x['id'],n)['players']},key=lambda v:int(v[1:])) for x in rows},
       'places':sorted({a for x in rows[:3] for n in x['rounds'][:4] for p in wb.load_round(x['id'],n)['players'].values() for a in p['area'] if a})})
    if route=='/api/workbench/supplement/status':return self.send(200,wb.supplement_status(q.get('id',[None])[0]))
    if route=='/api/workbench/agent/job':return self.send(200,wb.agent_get(q.get('id',[''])[0]))
   except (ValueError,OSError,KeyError) as e:return self.send(404,{'error':str(e)[:200]})
  if route.startswith('/api/demo/') or route=='/api/demos':
   from . import demo_review as dr
   from urllib.parse import parse_qs
   q=parse_qs(urlsplit(self.path).query);identifier=q.get('id',[''])[0]
   try:
    if route=='/api/demo/identities':
     from .demo_identity import library
     return self.send(200,{'matches':library()})
    if route.startswith('/api/demo/compare'):
     from . import demo_compare as dc
     if route=='/api/demo/compare/job':return self.send(200,dc.get(identifier))
     mid=q.get('match',[''])[0];n=int(q.get('round',['0'])[0]);side=q.get('side',['T'])[0]
     if route=='/api/demo/compare/pair':return self.send(200,dc.pair(mid,n,q.get('reference',[''])[0],int(q.get('reference_round',['0'])[0]),side))
     ens=q.get('ensure',[''])[0].split(':');ensure=(ens[0],int(ens[1])) if len(ens)==2 and ens[1].isdigit() else None
     return self.send(200,{**dc.retrieve(mid,n,side,ensure),'destination':dc.destination()})
    if route=='/api/demos':return self.send(200,{'samples':dr.samples(),'matches':dr.library()})
    if route=='/api/demo/cases':
     from .tactic_cases import search
     return self.send(200,search(q.get('q',[''])[0],q.get('map',[''])[0],q.get('side',[''])[0]))
    if route in ('/api/demo/case','/api/demo/case/learning'):
     from .tactic_cases import get,learning
     return self.send(200,learning(identifier) if route.endswith('/learning') else get(identifier))
    if route=='/api/demo/analysis':
     from .demo_match_coach import index
     return self.send(200,index(identifier))
    if route=='/api/demo/coach':
     from .demo_coach import get
     return self.send(200,get(identifier,int(q.get('round',['0'])[0])))
    if route=='/api/demo/job':return self.send(200,dr.state(identifier))
    if route=='/api/demo/result':return self.send(200,dr.result(identifier))
    if route=='/api/demo/round':return self.send(200,dr.round_data(identifier,int(q.get('round',['0'])[0])))
    if route=='/api/demo/players':
     from .demo_workbench import player_names
     dr.state(identifier);return self.send(200,{'names':player_names(identifier)})
    if route=='/api/demo/replay':
     from .demo_workbench import replay_round
     return self.send(200,replay_round(identifier,int(q.get('round',['0'])[0])))
    if route=='/api/demo/boards':return self.send(200,dr.boards(identifier))
   except (ValueError,OSError):return self.send(404,{'error':'比赛数据尚未就绪或不存在'})
  if route=='/api/media'  or route.startswith('/media/'):
   from pathlib import Path
   base=ROOT/'data/knowledge/metastack/media'
   if not (base/'index.json').exists():return self.send(404,{'error':'Media index unavailable'})
   media=json.loads((base/'index.json').read_text(encoding='utf-8'))
   if route=='/api/media':return self.send(200,media)
   name=route.removeprefix('/media/');allowed={f['file'] for item in media['items'] for f in item.get('images',[])+item.get('frames',[])}
   if name not in allowed:return self.send(404,{'error':'Unknown media'})
   path=(base/name).resolve()
   if not path.is_relative_to(base.resolve()) or path.suffix.lower() not in ['.jpg','.png','.webp']:return self.send(403,{'error':'Invalid media path'})
   return self.send(200,path.read_bytes(),{'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[path.suffix.lower()])
  if route.startswith('/icons/') and route.endswith('.svg'):
   # Equipment icons decompiled from the local CS2 install (data/icons, see experiments/import-icons.ps1); whitelist by file name.
   base=(ROOT/'data/icons/panorama/images/icons/equipment').resolve();name=route.split('/')[-1]
   path=(base/name).resolve()
   if not name.replace('_','').replace('.svg','').isalnum() or path.parent!=base or not path.exists():return self.send(404,{'error':'Unknown icon'})
   return self.send(200,path.read_bytes(),'image/svg+xml')
  if route.startswith('/api/lab/radar/'):
   from .radar_maps import metadata
   try:return self.send(200,metadata(route.split('/')[-1]))
   except (ValueError,OSError):return self.send(404,{'error':'雷达图尚未准备'})
  if route.startswith('/radar/') and route.endswith('.png'):
   from .radar_maps import image_path
   try:return self.send(200,image_path(route.split('/')[-1][:-4]).read_bytes(),'image/png')
   except (ValueError,OSError):return self.send(404,{'error':'雷达图不存在'})
  if route=='/api/lab/maps':
   from .free_lab import available
   return self.send(200,{'maps':available()})
  if route=='/api/lab/job':
   from urllib.parse import parse_qs
   from .free_lab import get
   try:return self.send(200,get(parse_qs(urlsplit(self.path).query).get('id',[''])[0]))
   except ValueError:return self.send(404,{'error':'实验不存在'})
  if route.startswith('/lab-maps/') and route.endswith('.bin'):
   from .free_lab import available,geometry
   name=route.split('/')[-1][:-4]
   if name not in available():return self.send(404,{'error':'地图不存在'})
   return self.send(200,geometry(name),'application/octet-stream')
  if route=='/api/solver':
   from .tactical_solver import latest
   return self.send(200,latest())
  if route=='/api/nuke':
   from .nuke_teaching import plan,teaching
   return self.send(200,{'plan':plan(),'teaching':teaching()})
  if route=='/maps/de_nuke.bin':
   from .strategy_review_server import geometry
   return self.send(200,geometry('de_nuke'),'application/octet-stream')
  if route in ['/vendor/three.module.js','/vendor/three.core.js','/vendor/OrbitControls.js']:
   return self.send(200,(ROOT/'web'/route.lstrip('/')).read_bytes(),'text/javascript')
  if route=='/api/research/job':
   from urllib.parse import parse_qs
   from .lineup_research import get_job
   try:return self.send(200,get_job(parse_qs(urlsplit(self.path).query).get('id',[''])[0]))
   except ValueError:return self.send(404,{'error':'研究任务不存在'})
  if route=='/api/research/catalog':
   from .lineup_catalog import load_catalog
   from .lineup_research import Research
   return self.send(200,{'cards':[Research.compact(c) for c in load_catalog()['cards']]})
  if route=='/api/status':
   from .provider import load_config
   try:config=load_config();model={'configured':True,'host':urlsplit(config['endpoint']).hostname}
   except (ValueError,OSError):model={'configured':False,'host':None}
   from .reach_sources import readiness
   return self.send(200,{'token':TOKEN,'model':model,'indexed':20,'verified_executable':0,'research_services':readiness()})
  static={'/demos':('demo-review.html','text/html'),'/demo-review.js':('demo-review.js','text/javascript'),'/demo-review.css':('demo-review.css','text/css'),'/lab':('free-lab.html','text/html'),'/free-lab.js':('free-lab.js','text/javascript'),'/free-lab.css':('free-lab.css','text/css'),'/assistant':('assistant.html','text/html'),'/assistant.js':('assistant.js','text/javascript'),'/assistant.css':('assistant.css','text/css'),'/':('demo-review.html','text/html'),'/demo-compare.js':('demo-compare.js','text/javascript'),'/demo-workbench.js':('demo-workbench.js','text/javascript'),'/mission.css':('mission.css','text/css'),'/replay-engine.js':('replay-engine.js','text/javascript'),'/cs-icons.js':('cs-icons.js','text/javascript'),'/tactic-board.js':('tactic-board.js','text/javascript'),'/player-hub.js':('player-hub.js','text/javascript'),'/i18n.js':('i18n.js','text/javascript'),'/i18n-en.js':('i18n-en.js','text/javascript'),'/demo-workbench.css':('demo-workbench.css','text/css'),'/tactics.css':('tactics.css','text/css'),'/nuke':('nuke-teaching.html','text/html'),'/nuke-teaching.js':('nuke-teaching.js','text/javascript'),'/solver':('free-lab.html','text/html'),'/lineups':('lineup-review.html','text/html'),'/lineup-review.js':('lineup-review.js','text/javascript')}
  if route in static:
   name,kind=static[route];return self.send(200,(ROOT/'web'/name).read_bytes(),kind+'; charset=utf-8')
  return self.send(404,{'error':'Not found'})
 def redirect(self,location):
  self.send_response(302);self.send_header('Location',location);self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers()
 def do_POST(self):
  if not self.permitted() or self.headers.get('X-Local-Token')!=TOKEN:return self.send(403,{'error':'请刷新本地页面'})
  route=urlsplit(self.path).path
  if route.startswith('/api/hub/') or route.startswith('/api/room/'):
   from . import player_hub as hub,tactic_room as room
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=600000:raise ValueError('请求大小超限')
    raw=json.loads(self.rfile.read(size))
    if not isinstance(raw,dict):raise ValueError('无效请求')
    if route=='/api/hub/account/manual':return self.send(200,hub.link_manual(raw.get('steamid')))
    if route=='/api/hub/unlink':return self.send(200,hub.unlink())
    if route=='/api/hub/settings':return self.send(200,hub.save_settings(raw))
    if route=='/api/hub/scan':return self.send(200,hub.scan_once())
    if route=='/api/hub/refresh':hub.refresh_profile();return self.send(200,hub.account())
    if route=='/api/hub/sharecodes/check':return self.send(200,hub.check_sharecodes())
    if route=='/api/room/tactic':return self.send(200,room.save(raw))
    if route=='/api/room/tactic/delete':return self.send(200,room.delete(raw.get('id')))
    if route=='/api/room/tactic/duplicate':return self.send(200,room.duplicate(raw.get('id')))
    if route=='/api/room/import_legacy':return self.send(200,room.import_legacy(raw.get('match'),raw.get('board')))
    return self.send(404,{'error':'Not found'})
   except RuntimeError as e:return self.send(409,{'error':str(e)[:200]})
   except (ValueError,KeyError,TypeError,OSError) as e:return self.send(400,{'error':str(e)[:200]})
  if route.startswith('/api/workbench/'):
   from . import demo_workbench as wb
   try:
    size=int(self.headers.get('Content-Length','0'))
    if not 0<size<=400000:raise ValueError('请求大小超限')
    raw=json.loads(self.rfile.read(size))
    if not isinstance(raw,dict):raise ValueError('无效请求')
    u=raw.get('unchecked',[]);ub=raw.get('unchecked_b',[])
    if route=='/api/workbench/query':return self.send(200,wb.run_query(raw['query'],u))
    if route=='/api/workbench/tracks':return self.send(200,wb.tracks(raw['query'],u,raw.get('offset',0),raw.get('limit',10),raw.get('include_enemies') is True))
    if route=='/api/workbench/zone':return self.send(200,wb.zone_rounds(raw['query'],u,raw['zone']))
    if route=='/api/workbench/heatmap':
     args=(raw.get('metric','dwell'),raw.get('floor','upper'),raw.get('cell',16))
     if raw.get('query_b') is not None:return self.send(200,wb.heat_compare(raw['query'],u,raw['query_b'],ub,*args))
     h=wb.heat_grid(raw['query'],u,*args);h.pop('_key',None);return self.send(200,h)
    if route=='/api/workbench/cell':
     g=raw.get('which','a');qq,uu=(raw['query_b'],ub) if g=='b' else (raw['query'],u)
     return self.send(200,wb.heat_cell(qq,uu,raw.get('metric','dwell'),raw.get('floor','upper'),raw.get('cell',16),int(raw['cx']),int(raw['cy']),raw.get('radius',0)))
    if route=='/api/workbench/grenades':
     if raw.get('query_b') is not None:return self.send(200,wb.grenade_compare(raw['query'],u,raw['query_b'],ub,raw.get('space_tol',160),raw.get('time_tol',5)))
     return self.send(200,wb.grenades(raw['query'],u,raw.get('space_tol',160),raw.get('time_tol',5),raw.get('kinds'),raw.get('both_sides') is True))
    if route=='/api/workbench/agent/preview':return self.send(200,wb.agent_preview(raw['query'],u,raw.get('query_b'),ub,raw.get('lang','zh')))
    if route=='/api/workbench/agent/start':return self.send(202,wb.agent_start(raw))
    if route=='/api/workbench/agent/cancel':return self.send(200,wb.agent_cancel(raw['id']))
    if route=='/api/workbench/supplement/start':
     ids=[m['id'] for m in wb.catalog() if (raw.get('all') is True and not m['capabilities']['economy']) or m['id']==raw.get('match')]
     if not ids:raise ValueError('没有需要补充解析的比赛')
     return self.send(202,wb.start_supplements(ids))
    if route=='/api/workbench/supplement/cancel':return self.send(200,wb.cancel_supplements(raw['id']))
    return self.send(404,{'error':'Not found'})
   except RuntimeError as e:return self.send(409,{'error':str(e)[:200]})
   except (ValueError,KeyError,TypeError,OSError) as e:return self.send(400,{'error':str(e)[:200]})
  if route.startswith('/api/demo/'):
   from . import demo_review as dr
   from urllib.parse import unquote
   try:
    size=int(self.headers.get('Content-Length','0'))
    if route=='/api/demo/upload':
     self.connection.settimeout(120)
     from .demo_identity import validate,set_identity
     kind=self.headers.get('X-Demo-Kind','unknown');source=unquote(self.headers.get('X-Demo-Source',''))
     validate(kind,source)
     uploaded=dr.upload(self.rfile,size,unquote(self.headers.get('X-Demo-Name','upload.dem')))
     set_identity(uploaded['id'],kind,source)
     return self.send(202,uploaded)
    if not 0<size<=(500000 if route=='/api/demo/board' else 8192):raise ValueError('请求大小超限')
    raw=json.loads(self.rfile.read(size))
    if route in ('/api/demo/analysis/start','/api/demo/analysis/cancel'):
     from .demo_match_coach import start,cancel
     return self.send(202,start(raw) if route.endswith('/start') else cancel(raw))
    if route in ('/api/demo/coach/start','/api/demo/coach/cancel'):
     from .demo_coach import start,cancel
     return self.send(202,start(raw) if route.endswith('/start') else cancel(raw))
    if route=='/api/demo/identity':
     from .demo_identity import set_identity
     return self.send(200,set_identity(raw['match'],raw['kind'],raw.get('source_url','')))
    if route in ('/api/demo/compare/start','/api/demo/compare/cancel'):
     from .demo_compare import start,cancel
     return self.send(202,start(raw) if route.endswith('/start') else cancel(raw['id']))
    if route=='/api/demo/start':return self.send(202,dr.start_sample(raw))
    if route=='/api/demo/cancel':return self.send(200,dr.cancel(raw['id']))
    if route=='/api/demo/board':return self.send(200,dr.save_board(raw))
    return self.send(404,{'error':'Not found'})
   except RuntimeError as e:return self.send(409,{'error':str(e)})
   except (ValueError,KeyError,OSError,TypeError) as e:
    self.close_connection=True
    return self.send(400,{'error':str(e)[:150]})
  if route not in ['/api/search','/api/preview','/api/generate','/api/nuke/check','/api/solver/check','/api/research/start','/api/research/cancel','/api/research/resume','/api/lab/start','/api/lab/cancel','/api/lab/surface']:return self.send(404,{'error':'Not found'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=8192:raise ValueError('Invalid request size')
   raw=json.loads(self.rfile.read(size))
   if route in ['/api/lab/start','/api/lab/cancel','/api/lab/surface']:
    from .free_lab import start,cancel,surfaces
    try:return self.send(200 if route.endswith('/surface') else 202,surfaces(raw) if route.endswith('/surface') else start(raw) if route.endswith('/start') else cancel(raw['id']))
    except RuntimeError:return self.send(409,{'error':'已有实验正在计算'})
   if route.startswith('/api/research/'):
    from .lineup_research import start_job,cancel_job,RUNS
    if route=='/api/research/start':
     try:return self.send(202,start_job(raw))
     except RuntimeError:return self.send(409,{'error':'已有研究任务在运行；可先取消它'})
    if not isinstance(raw,dict) or set(raw)!={'id'}:raise ValueError('Invalid job action')
    if route=='/api/research/cancel':return self.send(200,cancel_job(raw['id']))
    import re
    if not isinstance(raw['id'],str) or not re.fullmatch(r'[0-9a-f]{32}',raw['id']):raise ValueError('Invalid job id')
    path=RUNS/raw['id']/'research.json'
    if not path.exists():raise ValueError('Unknown job')
    request=json.loads(path.read_text(encoding='utf-8'))['request']
    try:return self.send(202,start_job(request,raw['id']))
    except RuntimeError:return self.send(409,{'error':'已有研究任务在运行'})
   if route=='/api/solver/check':
    from .tactical_solver import check_latest
    return self.send(200,check_latest(raw))
   if route=='/api/nuke/check':
    from .nuke_teaching import check
    return self.send(200,check(raw))
   if route=='/api/search':return self.send(200,retrieve(raw))
   if route=='/api/preview':return self.send(200,packet(raw))
   if not LOCK.acquire(blocking=False):return self.send(409,{'error':'已有一次模型调用正在执行'})
   try:return self.send(200,generate(raw))
   finally:LOCK.release()
  except (ValueError,TypeError,KeyError):return self.send(400,{'error':'条件或模型输出未通过校验；没有生成可执行战术'})
  except Exception:return self.send(502,{'error':'模型服务未完成请求；本地检索仍可使用'})
class Server(ThreadingHTTPServer):
 def server_bind(self):TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
if __name__=='__main__':
 build_index()
 from .player_hub import start_watcher
 start_watcher()
 server=Server(('127.0.0.1',PORT),Handler);print(f'Tactics library: http://127.0.0.1:{PORT}',flush=True);server.serve_forever()
