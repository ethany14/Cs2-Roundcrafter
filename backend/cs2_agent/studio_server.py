"""Loopback-only server for the decision studio; Eregion plans run in a bounded job."""
import gzip
import json
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
from .casebook import ROOT
from .studio import DIRECTORY

PORT=8788;TOKEN=secrets.token_hex(24);JOBS={};LOCK=threading.Lock()


def model_status():
    from .provider import load_config
    try:
        config=load_config();return {'configured':True,'host':urlsplit(config['endpoint']).hostname,'max_calls':5}
    except (ValueError,OSError):return {'configured':False,'host':None,'max_calls':5}


def clip_ids():return {row['id'] for row in json.loads((DIRECTORY/'index.json').read_text(encoding='utf-8'))}


def run_job(identifier):
    from .studio_planner import generate
    def progress(message):
        with LOCK:JOBS[identifier]['message']=message
    try:
        result=generate(identifier,progress)
        with LOCK:JOBS[identifier]={'status':'done','result':result}
    except Exception as e:
        # Transport error text can contain provider details; never return raw exception bodies.
        with LOCK:JOBS[identifier]={'status':'error','message':'方案生成未完成。可重试；原始复现仍可使用。','error_type':type(e).__name__}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,content_type='application/json; charset=utf-8'):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        if len(data)>4000 and 'gzip' in self.headers.get('Accept-Encoding',''):
            data=gzip.compress(data,compresslevel=2);self.send_header('Content-Encoding','gzip');self.send_header('Vary','Accept-Encoding')
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def permitted(self):
        hosts={f'127.0.0.1:{PORT}',f'localhost:{PORT}'}
        return self.headers.get('Host') in hosts and self.headers.get('Origin') in (None,*('http://'+h for h in hosts))
    def do_GET(self):
        if not self.permitted():return self.send(403,{'error':'仅允许本机页面访问'})
        route=urlsplit(self.path).path
        try:
            if route=='/api/status':return self.send(200,{'token':TOKEN,'ai':model_status()})
            if route=='/api/clips':return self.send(200,json.loads((DIRECTORY/'index.json').read_text(encoding='utf-8')))
            for prefix in ('/api/clips/','/api/jobs/','/api/planning-preview/'):
                if route.startswith(prefix):
                    identifier=route[len(prefix):]
                    if identifier not in clip_ids():return self.send(404,{'error':'片段不存在'})
                    if prefix=='/api/jobs/':
                        with LOCK:job=JOBS.get(identifier,{'status':'idle'}).copy()
                        return self.send(200,job)
                    if prefix=='/api/planning-preview/':
                        from .studio_planner import planning_packet
                        return self.send(200,planning_packet(identifier))
                    payload=json.loads((DIRECTORY/(identifier+'.json')).read_text(encoding='utf-8'))
                    from .studio_planner import cached_plans
                    result=cached_plans(identifier)
                    if result:
                        payload['plans']=result['plans'];payload['plan_source']=result['source']
                        payload['plan_validation']=result.get('validation_note','')
                        payload['fact_corrections']=result.get('fact_corrections',[])
                    return self.send(200,payload)
            static={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/vendor/three.module.js':'vendor/three.module.js','/vendor/three.core.js':'vendor/three.core.js','/vendor/OrbitControls.js':'vendor/OrbitControls.js'}
            if route in static:
                path=ROOT/'web'/static[route];kind='text/javascript' if path.suffix=='.js' else mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                return self.send(200,path.read_bytes(),kind+'; charset=utf-8')
            if route in ('/assets/map.bin','/assets/map.json'):
                path=DIRECTORY/route.split('/')[-1];return self.send(200,path.read_bytes(),'application/octet-stream' if path.suffix=='.bin' else 'application/json')
            return self.send(404,{'error':'页面不存在'})
        except (OSError,ValueError,KeyError):return self.send(500,{'error':'本地数据不可用，请重新构建实验数据'})
    def do_POST(self):
        if not self.permitted() or self.headers.get('X-Local-Token')!=TOKEN:return self.send(403,{'error':'请刷新本地页面'})
        if urlsplit(self.path).path!='/api/generate':return self.send(404,{'error':'接口不存在'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<1024:return self.send(400,{'error':'请求无效'})
            data=json.loads(self.rfile.read(length));identifier=data['case_id']
            if identifier not in clip_ids() or data.get('use_configured_model') is not True:return self.send(400,{'error':'请选择片段及模型生成操作'})
            if not model_status()['configured']:return self.send(409,{'error':'请先配置项目 .env 中的模型'})
            with LOCK:
                if any(j['status']=='running' for j in JOBS.values()):return self.send(409,{'error':'已有生成任务正在运行'})
                JOBS[identifier]={'status':'running','message':'Agent 正在准备局势证据'}
            threading.Thread(target=run_job,args=(identifier,),daemon=True).start()
            return self.send(202,{'status':'running'})
        except (ValueError,KeyError,TypeError):return self.send(400,{'error':'请求无效'})


def main():
    if not (DIRECTORY/'index.json').exists():
        from .studio import build
        build()
    print(f'CS2 Decision Studio: http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()


if __name__=='__main__':main()
