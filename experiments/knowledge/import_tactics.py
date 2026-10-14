"""Import public source metadata, never infer unobserved video instructions."""
import hashlib,json,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'data/knowledge/cs2app';BASE='https://www.cs2.app'
class Node:
 def __init__(self,tag='',attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[]
 def text(self):return ' '.join(c if isinstance(c,str) else c.text() for c in self.children).strip()
 def find(self,predicate):
  return ([self] if predicate(self) else [])+[n for c in self.children if isinstance(c,Node) for n in c.find(predicate)]
class DOM(HTMLParser):
 def __init__(self,s):super().__init__();self.root=Node();self.stack=[self.root];self.feed(s)
 def handle_starttag(self,tag,attrs):
  n=Node(tag,attrs);self.stack[-1].children.append(n)
  if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:self.stack.append(n)
 def handle_endtag(self,tag):
  for i in range(len(self.stack)-1,0,-1):
   if self.stack[i].tag==tag:self.stack=self.stack[:i];break
 def handle_data(self,data):self.stack[-1].children.append(data)
def fetch(url,path):
 if not path.exists():
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'RoundCrafter-source-index/0.1'}),timeout=30) as r:path.write_bytes(r.read(2_000_000))
 return path.read_text(encoding='utf-8')
def main():
 (OUT/'raw').mkdir(parents=True,exist_ok=True);html=fetch(BASE+'/tactics-directory',OUT/'raw/directory.html');root=DOM(html).root;items=root.find(lambda n:n.attrs.get('role')=='listitem');cards=[]
 for item in items:
  links=item.find(lambda n:n.tag=='a' and n.attrs.get('href','').startswith('/tactics-directory/'))
  if not links:continue
  link=links[0];url=BASE+link.attrs['href'];slug=url.rsplit('/',1)[-1];detail=fetch(url,OUT/'raw'/f'{slug}.html');doc=DOM(detail).root
  headings=doc.find(lambda n:n.tag=='h1');title=headings[0].text() if headings else slug
  tags=[n.text() for n in link.find(lambda n:'fs-cmsfilter-field' in n.attrs)]
  maps=['Mirage','Inferno','Vertigo','Nuke','Ancient','Anubis','Dust2','Overpass'];map_name=next((s for s in tags if s in maps),None);side=next((s for s in tags if s in ['Terrorist','Counter-Terrorist']),None);economy=next((s for s in tags if s in ['Pistol','Rifle','Eco','Force']),None);typ=next((s for s in tags if s in ['Execute','Rush','Explode','Split','Wrap','Fake','Setup']),None)
  if not all([map_name,side,economy,typ]):raise ValueError('Missing source tags '+slug+str(tags))
  metas=doc.find(lambda n:n.tag=='meta' and n.attrs.get('name')=='description');summary=metas[0].attrs.get('content','') if metas else ''; descriptions=doc.find(lambda n:'rich-text-block' in n.attrs.get('class','').split()); summary=descriptions[0].text() if descriptions else summary
  videos=[]
  for m in re.findall(r'(?:tube\.rvere\.com/embed\?v=|youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})',detail+html[0:0]):
   if m not in videos:videos.append(m)
  if not videos:
   for n in item.find(lambda n:n.tag=='iframe'):
    m=re.search(r'[?&]v=([A-Za-z0-9_-]{11})',n.attrs.get('src',''))
    if m:videos.append(m[1])
  card={'id':slug,'title':title,'map':'de_'+map_name.lower(),'side':'CT' if side=='Counter-Terrorist' else 'T','economy':economy.lower(),'type':typ.lower(),'source_url':url,'source_description':summary,'videos':['https://www.youtube.com/watch?v='+v for v in dict.fromkeys(videos)],'retrieved_at':datetime.now(timezone.utc).isoformat(),'source_sha256':hashlib.sha256(detail.encode()).hexdigest(),'verification':{'metadata':True,'video':False,'current_map':False,'execution':False},'requirements':{'players':None,'utility':None,'weapons':None,'spawn':None,'coordination':None},'steps':[],'fallbacks':[],'source_timecodes':[],'review_notes':[]}
  cards.append(card);print(slug,map_name,economy,len(videos),flush=True)
 (OUT/'cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2),encoding='utf-8');print('DONE',len(cards),flush=True)
if __name__=='__main__':main()
