"""Application-owned public search/read transports. Search snippets are never evidence."""
from dataclasses import asdict
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import urlsplit, urlunsplit, urljoin, urlencode
from xml.etree import ElementTree
import httpx
from .casebook import ROOT
from .lineup_catalog import canonical_url, now, write_json, Evidence

CACHE=ROOT/'data/knowledge/lineups/cache'
CACHE_LOCK=threading.RLock()

class ResearchStop(Exception):
    def __init__(self,status):self.status=status;super().__init__(status)

class Budget:
    def __init__(self,whole=False,cancelled=None,state=None,save=lambda:None):
        self.state=state if state is not None else {}
        self.state.setdefault('limits',{'search':12 if whole else 3,'read':24 if whole else 8,'wall_seconds':360 if whole else 180})
        self.state.setdefault('used',{'search':0,'read':0,'cache_hits':0})
        self.state.setdefault('events',[])
        self.cancelled=cancelled or threading.Event();self.save=save
        self.started=time.monotonic();self.elapsed_before=self.state.get('elapsed_seconds',0)
    def check(self):
        if self.cancelled.is_set():raise ResearchStop('cancelled')
        if self.elapsed_before+time.monotonic()-self.started>=self.state['limits']['wall_seconds']:raise ResearchStop('budget_exhausted')
    def reserve(self,kind,url):
        self.check()
        if self.state['used'][kind]>=self.state['limits'][kind]:raise ResearchStop('budget_exhausted')
        self.state['used'][kind]+=1
        self.event(kind,url,'reserved')
    def event(self,kind,url,status,**details):
        self.state['elapsed_seconds']=round(self.elapsed_before+time.monotonic()-self.started,3)
        self.state['events'].append({'at':now(),'kind':kind,'destination':url,'status':status,**details})
        self.save()

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden=0;self.title=False;self.title_parts=[];self.parts=[];self.links=[];self.videos=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in {'script','style','noscript','svg'}:self.hidden+=1
        if tag=='title':self.title=True
        if tag=='a' and a.get('href'):self.links.append(a['href'])
        if tag=='iframe' and a.get('src'):self.videos.append(a['src'])
        if tag in {'p','div','li','br','h1','h2','h3','tr'}:self.parts.append('\n')
        if tag=='meta' and a.get('property') in {'og:video','og:video:url'}:self.videos.append(a.get('content',''))
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','svg'}:self.hidden=max(0,self.hidden-1)
        if tag=='title':self.title=False
    def handle_data(self,data):
        if not self.hidden:
            if self.title:self.title_parts.append(data)
            else:self.parts.append(data)

def public_url(url):
    canonical_url(url)  # Validate independently of the transport authority.
    parsed=urlsplit(url)
    host=parsed.hostname
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private/local source addresses are not permitted')
    # www and bare hosts may serve different content; normalization is a cache identity,
    # not permission to change the actual requested transport hostname.
    return urlunsplit(('https',parsed.netloc,parsed.path or '/',parsed.query,''))

class Sources:
    def __init__(self,budget,cache=CACHE,client=None):
        self.budget=budget;self.cache=cache
        self.client=client or httpx.Client(timeout=httpx.Timeout(15,connect=5),follow_redirects=False,
                                          headers={'User-Agent':'Debrief-Research/1.0 (public learning references)'})
        self.discovered=set()
    def close(self):self.client.close()
    def _cached(self,kind,key):
        path=self.cache/(hashlib.sha256((kind+key).encode()).hexdigest()+'.json')
        with CACHE_LOCK:
            if path.exists():
                value=json.loads(path.read_text(encoding='utf-8'))
                ttl=7*86400 if value.get('status') in {'read','found','not_found'} else 300
                if time.time()-path.stat().st_mtime<ttl:
                    self.budget.check();self.budget.state['used']['cache_hits']+=1
                    self.budget.event(kind,key,'cache_hit',cached_status=value['status'])
                    return path,{**value,'cache_hit':True}
        return path,None
    def _store(self,path,value):
        self.budget.check()
        with CACHE_LOCK:write_json(path,value)
        return value
    def _get(self,url):
        # Recheck every redirect, stream with bounded size, never forward credentials.
        for _ in range(4):
            self.budget.check();url=public_url(url)
            self.budget.state['used']['http_requests']=self.budget.state['used'].get('http_requests',0)+1
            with self.client.stream('GET',url) as r:
                if r.status_code in {301,302,303,307,308}:
                    url=urljoin(url,r.headers.get('location',''));continue
                if r.status_code!=200:return {'status':'inaccessible','http_status':r.status_code,'url':url}
                mime=r.headers.get('content-type','').lower()
                if not any(x in mime for x in ['html','text','xml','json']):return {'status':'unsupported_content','url':url}
                body=bytearray()
                for chunk in r.iter_bytes():
                    self.budget.check();body.extend(chunk)
                    if len(body)>1_000_000:return {'status':'content_too_large','url':url}
                return {'status':'ok','url':url,'text':body.decode('utf-8',errors='replace')}
        return {'status':'inaccessible','reason':'redirect_limit','url':url}
    def search(self,query):
        query=query.strip()[:300]
        if not query:raise ValueError('Search query required')
        path,cached=self._cached('search','bing:v2:'+query)
        if cached:
            self.discovered.update(x['url'] for x in cached.get('results',[]));return cached
        endpoint='https://www.bing.com/search?'+urlencode({'format':'rss','q':query})
        self.budget.reserve('search',endpoint)
        try:
            r=self._get(endpoint)
            if r['status']!='ok':result={**r,'results':[]}
            else:
                xml=ElementTree.fromstring(r['text']);seen=set();rows=[]
                for item in xml.findall('./channel/item'):
                    try:url=canonical_url(item.findtext('link',''))
                    except ValueError:continue
                    if url in seen:continue
                    seen.add(url)
                    rows.append({'url':url,'title':item.findtext('title','')[:200],
                                 'snippet':item.findtext('description','')[:600],'evidence_status':'discovery_only'})
                result={'status':'found' if rows else 'not_found','results':rows[:10]}
        except (httpx.HTTPError,OSError,ValueError,ElementTree.ParseError) as exc:
            result={'status':'search_unavailable','reason':type(exc).__name__,'results':[]}
        result.update(query=query,provider='bing_public_rss',observed_at=now())
        self.discovered.update(x['url'] for x in result['results'])
        self.budget.event('search',endpoint,result['status'],results=len(result['results']))
        return self._store(path,result)
    def read(self,url):
        url=canonical_url(url)
        path,cached=self._cached('read',url)
        if cached:return cached
        self.budget.reserve('read',url)
        try:
            r=self._get(url)
            if r['status']!='ok':result=r
            else:
                p=PageParser();p.feed(r['text'])
                text=re.sub(r'[ \t\r\f\v]+',' ',''.join(p.parts));text=re.sub(r'\n\s*\n+','\n',text).strip()[:50000]
                title=''.join(p.title_parts).strip()
                if re.search(r'just a moment|access denied|verify you are human|sign in to continue',title,re.I):
                    result={'status':'inaccessible','reason':'challenge_or_login','url':url}
                elif len(text)<80:result={'status':'insufficient_evidence','reason':'empty_or_script_shell','url':url,'title':title}
                else:
                    videos=[]
                    for link in p.videos+p.links:
                        if re.search(r'^https://(?:www\.)?(?:youtube(?:-nocookie)?\.com/(?:embed/|watch\?)|youtu\.be/)',link):
                            try:videos.append(canonical_url(link))
                            except ValueError:pass
                    links=[]
                    for link in p.links:
                        try:links.append(canonical_url(urljoin(r['url'],link)))
                        except ValueError:pass
                    result={'status':'read','url':url,'final_url':r['url'],'title':title,'text':text,
                            'videos':list(dict.fromkeys(videos)),'links':list(dict.fromkeys(links))[:80],
                            'content_hash':hashlib.sha256(r['text'].encode()).hexdigest(),
                            'scope':'visible_html_text_and_embed_links_only; no video viewing',
                            'observed_at':now()}
        except (httpx.HTTPError,OSError,ValueError) as exc:
            result={'status':'inaccessible','reason':type(exc).__name__,'url':url}
        result.setdefault('observed_at',now())
        self.budget.event('read',url,result['status'])
        return self._store(path,result)

def extract_metadata(card,page):
    """Conservative source adapter. Never extracts coordinates or unobserved video actions."""
    if page.get('status')!='read':return card
    card=json.loads(json.dumps(card))
    # Only the exact source can enrich an existing identity. Other pages remain separate references.
    if canonical_url(page['url'])!=canonical_url(card['source_url']):return card
    card['source_status']='page_read_metadata_only'
    text=page['text']
    facts={}
    for key,choices in [('motion',['Standing','Running','Crouched']),('throw',['Jump Throw','Normal Throw'])]:
        values=[v for v in choices if re.search(r'\b'+re.escape(v)+r'\b',text)]
        if len(values)==1:facts[key]=values[0]
    if page.get('videos') and len(page['videos'])==1:facts['video_url']=page['videos'][0]
    for key,value in facts.items():
        old=card.get(key)
        conflict=[{'old':old,'new':value}] if old is not None and old!=value else []
        excerpt=value if key!='video_url' else 'iframe/link: '+value
        ev=asdict(Evidence('read-'+page['content_hash'][:12]+'-'+key,page['url'],key,value,excerpt,
                          'public_http_html',page['observed_at'],page['content_hash'],contradictions=conflict))
        card['evidence']=[e for e in card['evidence'] if not(e['field']==key and e['method']=='public_http_html')]+[ev]
        if not conflict:card[key]=value
    return card

def accept_field_evidence(card,page,proposals):
    """Optional model extraction: exact quotes, allowed fields and literal values only.

    Arbitrary model text cannot become coordinates, seconds or game validation.
    The caller must separately confirm the page's map/start/target identity.
    """
    if page.get('status')!='read':raise ValueError('Source not actually read')
    sources={canonical_url(card['source_url'])}
    if card.get('video_url'):sources.add(canonical_url(card['video_url']))
    if canonical_url(page['url']) not in sources:raise ValueError('Source identity mismatch')
    allowed={'motion','throw','steps'}
    accepted=[]
    for p in proposals[:12]:
        key=p.get('field');value=p.get('value');quote=p.get('quote','')
        if key not in allowed or not isinstance(value,str) or not isinstance(quote,str) or not 8<=len(quote)<=800:
            raise ValueError('Unsupported extraction')
        if quote not in page['text'] or value not in quote:raise ValueError('Unbacked extraction')
        if key=='motion' and value not in {'Standing','Running','Crouched'}:raise ValueError('Invalid motion')
        if key=='throw' and value not in {'Jump Throw','Normal Throw'}:raise ValueError('Invalid throw')
        if key=='steps' and (value==page.get('title') or len(value)<20):raise ValueError('Title is not an instruction')
        accepted.append(asdict(Evidence('quote-'+hashlib.sha256((key+quote).encode()).hexdigest()[:16],page['url'],key,value,quote,
            'literal_model_extraction',page['observed_at'],page['content_hash'],scope='literal_text_only')))
    return accepted
