"""Read-only loopback review UI; observer positions require a separate explicit request."""
import json,mimetypes
from functools import lru_cache
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from socketserver import TCPServer
from urllib.parse import urlsplit
import numpy as np
from .casebook import ROOT
DATA=ROOT/'outputs/movement/strategy/review';PORT=8789
@lru_cache(maxsize=7)
def geometry(name):
 path=ROOT/'data/maps/all'/name/'scene.npz'
 with np.load(path) as d:tri=d['triangles'].astype('<f4')
 return tri.tobytes()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,code,value,kind='application/json; charset=utf-8'):
  value=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(value)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(value)
 def do_GET(self):
  if self.headers.get('Host') not in (f'127.0.0.1:{PORT}',f'localhost:{PORT}'):return self.send(403,{'error':'Local only'})
  route=urlsplit(self.path).path
  try:
   index=json.loads((DATA/'index.json').read_text());ids={r['id'] for r in index};maps={r['map'] for r in index}
   if route=='/api/cases':return self.send(200,index)
   if route.startswith('/api/case/'):
    key=route.split('/')[-1];observer=key.endswith('-observer');base=key.removesuffix('-observer')
    if base not in ids:return self.send(404,{'error':'Unknown case'})
    return self.send(200,json.loads((DATA/(key+'.json')).read_text()))
   if route.startswith('/maps/'):
    name=route.split('/')[-1].removesuffix('.bin')
    if name not in maps:return self.send(404,{'error':'Unknown map'})
    return self.send(200,geometry(name),'application/octet-stream')
   static={'/':'strategy-review.html','/strategy-review.js':'strategy-review.js','/strategy-review.css':'strategy-review.css','/vendor/three.module.js':'vendor/three.module.js','/vendor/three.core.js':'vendor/three.core.js','/vendor/OrbitControls.js':'vendor/OrbitControls.js'}
   if route in static:
    path=ROOT/'web'/static[route];return self.send(200,path.read_bytes(),('text/javascript' if path.suffix=='.js' else mimetypes.guess_type(path.name)[0] or 'text/plain')+'; charset=utf-8')
   return self.send(404,{'error':'Not found'})
  except (OSError,ValueError,KeyError):return self.send(500,{'error':'Review data unavailable'})
class LocalServer(ThreadingHTTPServer):
 def server_bind(self):
  # HTTPServer's reverse DNS lookup can stall startup on offline Windows hosts.
  TCPServer.server_bind(self);self.server_name='localhost';self.server_port=self.server_address[1]
if __name__=='__main__':
 server=LocalServer(('127.0.0.1',PORT),Handler)
 print(f'Strategy review: http://127.0.0.1:{PORT}',flush=True);server.serve_forever()
