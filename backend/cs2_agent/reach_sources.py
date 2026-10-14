"""Agent-Reach's pinned channel choices, bounded inside the existing application.

Only public yt-dlp search/metadata/captions, bili-cli search/video and Jina Reader.
No downloader, account commands, browser cookies, paid transcription or global config.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit,parse_qs
from .casebook import ROOT
from .lineup_catalog import canonical_url, now
from .lineup_sources import ResearchStop, public_url

REACH_COMMIT='94f06c1969dfc1834001269d79d3ad0972d9dee6'
def readiness():
    return {'agent_reach':bool(importlib.util.find_spec('agent_reach')),'agent_reach_commit':REACH_COMMIT,
            'youtube':bool(importlib.util.find_spec('yt_dlp')),'bilibili':bool(importlib.util.find_spec('bili_cli')),
            'web_reader':'jina_reader','public_search':'bing_public_rss',
            'note':'Installed backends only; each task records actual source success/failure. Bilibili subtitles need an explicitly authorized browser/session; not enabled.'}

class ReachSources:
    def __init__(self,sources):self.sources=sources;self.budget=sources.budget
    def _command(self,argv,timeout=35):
        work=ROOT/'work/lineup-reach';work.mkdir(parents=True,exist_ok=True)
        # No shell interpolation, no inherited yt-dlp config, no raw output in logs.
        env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','NO_COLOR':'1'}
        with tempfile.TemporaryFile(dir=work) as out,tempfile.TemporaryFile(dir=work) as err:
            proc=subprocess.Popen(argv,stdout=out,stderr=err,stdin=subprocess.DEVNULL,env=env,cwd=work,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            deadline=time.monotonic()+timeout
            try:
                while proc.poll() is None:
                    self.budget.check()
                    if time.monotonic()>deadline:
                        proc.kill();proc.wait();return {'status':'inaccessible','reason':'backend_timeout'}
                    if os.fstat(out.fileno()).st_size>2_000_000 or os.fstat(err.fileno()).st_size>100_000:
                        proc.kill();proc.wait();return {'status':'content_too_large'}
                    time.sleep(.1)
                if proc.returncode:
                    err.seek(0);message=err.read(100000).decode('utf-8',errors='replace').lower()
                    out.seek(0);message+=' '+out.read(100000).decode('utf-8',errors='replace').lower()
                    reason='bot_or_rate_limit' if re.search(r'bot|429|412|sign in|403',message) else 'backend_error'
                    status_match=re.search(r'(?:状态码|http|status)[^0-9]{0,12}(403|412|429)',message)
                    return {'status':'inaccessible','reason':reason,'exit_code':proc.returncode,
                            'http_status':int(status_match[1]) if status_match else None}
                out.seek(0);return {'status':'ok','data':json.loads(out.read(2_000_000))}
            except BaseException:
                if proc.poll() is None:proc.kill();proc.wait()
                raise
    @staticmethod
    def ytdlp_args():
        return [sys.executable,'-m','yt_dlp','--ignore-config','--skip-download','--no-playlist','--no-warnings',
                '--socket-timeout','8','--retries','0','--extractor-retries','0','--js-runtimes','node',
                '--dump-single-json']
    def search(self,platform,query):
        if platform not in {'youtube','bilibili'}:raise ValueError('Unsupported channel')
        path,cached=self.sources._cached('search','reach:v2:'+platform+':'+query)
        if cached:
            self.sources.discovered.update(x['url'] for x in cached.get('results',[]));return cached
        self.budget.reserve('search',platform+' via Agent-Reach')
        try:
            if platform=='youtube':
                r=self._command([a for a in self.ytdlp_args() if a!='--no-playlist']+['--flat-playlist','--playlist-end','5','ytsearch5:'+query[:300]])
                entries=r.get('data',{}).get('entries',[]) if r['status']=='ok' else []
                rows=[{'url':'https://www.youtube.com/watch?v='+v['id'],'title':v.get('title',''),
                       'snippet':v.get('description','') or '','evidence_status':'discovery_only'} for v in entries if re.fullmatch(r'[\w-]{11}',v.get('id',''))]
            else:
                # Reviewed upstream search uses credential=None and never loads account/browser data.
                r=self._command([sys.executable,'-m','bili_cli.cli','search',query[:300],'--type','video','-n','5','--json'])
                entries=r.get('data',[]) if r['status']=='ok' else []
                if isinstance(entries,dict):entries=entries.get('data',entries.get('results',[]))
                rows=[]
                for v in entries:
                    vid=v.get('bvid','')
                    if re.fullmatch(r'BV[0-9A-Za-z]{10}',vid):rows.append({'url':'https://www.bilibili.com/video/'+vid,
                        'title':re.sub('<[^>]+>','',v.get('title','')),'snippet':v.get('description',v.get('desc','')) or '',
                        'evidence_status':'discovery_only'})
            result={'status':'found' if rows else 'not_found','results':rows} if r['status']=='ok' else {**r,'results':[]}
        except (OSError,ValueError,TypeError,KeyError) as exc:result={'status':'search_unavailable','reason':type(exc).__name__,'results':[]}
        result.update(provider='agent_reach/'+platform,observed_at=now(),query=query)
        self.sources.discovered.update(x['url'] for x in result['results'])
        self.budget.event('search',platform+' via Agent-Reach',result['status'],results=len(result['results']),
                          underlying_http_requests='unknown (bounded backend timeout/retries)')
        return self.sources._store(path,result)
    def read_video(self,url):
        url=canonical_url(url);p=urlsplit(url)
        if p.hostname not in {'www.youtube.com','youtube.com','bilibili.com','www.bilibili.com'}:raise ValueError('Unsupported video host')
        path,cached=self.sources._cached('read','reach:'+url)
        if cached:return cached
        self.budget.reserve('read',url)
        try:
            if 'youtube.com' in p.hostname:
                vid=parse_qs(p.query).get('v',[''])[0]
                if not re.fullmatch(r'[\w-]{11}',vid):raise ValueError('Invalid video ID')
                r=self._command(self.ytdlp_args()+[url])
                d=r.get('data',{})
                description=d.get('description','') or ''
                subs=d.get('subtitles') or d.get('automatic_captions') or {}
                # Signed caption endpoints remain private transport data, never included in reports.
                subtitle=next((s for lang in ['en','en-orig','zh-Hans','zh','zh-Hant'] for s in subs.get(lang,[]) if s.get('ext')=='json3'),None)
                transcript=[];caption_status='not_available'
                if r['status']=='ok' and subtitle:
                    caption_status='inaccessible'
                    self.budget.reserve('read','YouTube caption text endpoint (URL redacted)')
                    source=public_url(subtitle['url'])
                    with self.sources.client.stream('GET',source) as resp:
                        if resp.status_code==200:
                            body=bytearray()
                            for chunk in resp.iter_bytes():
                                self.budget.check();body.extend(chunk)
                                if len(body)>300000:raise ValueError('Caption text too large')
                            caption=json.loads(body)
                            transcript=[{'start_seconds':e.get('tStartMs',0)/1000,'text':''.join(s.get('utf8','') for s in e.get('segs',[])).strip()} for e in caption.get('events',[]) if e.get('segs')][:300]
                            caption_status='read' if transcript else 'empty_response'
                    self.budget.event('read','YouTube caption text endpoint (URL redacted)',caption_status)
                result={'status':'read','url':url,'title':d.get('title',''),'text':description[:16000],
                        'transcript':transcript,'caption_status':caption_status,'videos':[],
                        'scope':'yt-dlp video metadata'+(' and actual captions' if transcript else ' only')+'; no frames watched',
                        'content_hash':hashlib.sha256(json.dumps({'description':description,'transcript':transcript},ensure_ascii=False).encode()).hexdigest()}
            else:
                match=re.search(r'/video/(BV[0-9A-Za-z]{10})',p.path)
                if not match:raise ValueError('Invalid Bilibili video')
                # Do not pass subtitle/AI/comments flags: they trigger optional saved credential loading upstream.
                r=self._command([sys.executable,'-m','bili_cli.cli','video',match[1],'--json'])
                d=r.get('data',{});d=d.get('data',d);d=d.get('video',d)
                description=d.get('description',d.get('desc','')) or ''
                result={'status':'read','url':url,'title':d.get('title',''),'text':description[:16000],'transcript':[],
                        'caption_status':'requires_authorized_browser_channel','videos':[],
                        'scope':'bili-cli public video details only; no subtitles/frames watched',
                        'content_hash':hashlib.sha256(description.encode()).hexdigest()}
            if r['status']!='ok':result={k:v for k,v in r.items() if k!='data'}|{'url':url}
        except ResearchStop:raise
        except Exception as exc:result={'status':'inaccessible','reason':type(exc).__name__,'url':url}
        result.update(observed_at=now(),provider='agent_reach/video')
        self.budget.event('read',url,result['status'],underlying_http_requests='unknown (bounded backend timeout/retries)')
        return self.sources._store(path,result)
    def read_web(self,url):
        url=public_url(url)
        path,cached=self.sources._cached('read','jina:v2:'+url)
        if cached:return cached
        self.budget.reserve('read','https://r.jina.ai/'+url)
        try:
            r=self.sources._get('https://r.jina.ai/'+url)
            text=r.get('text','')
            if r['status']!='ok':result=r|{'url':url}
            elif re.search(r'Warning: Target URL returned error|just a moment|verify you are human|access denied',text,re.I):
                result={'status':'inaccessible','url':url,'reason':'reader_target_challenge'}
            elif 'Markdown Content:' not in text or len(text.split('Markdown Content:',1)[1].strip())<80:
                result={'status':'insufficient_evidence','url':url,'reason':'reader_empty_content'}
            elif 'cookie' in text.split('Markdown Content:',1)[1].lower() and not re.search(r'nuke|throw|smoke|standing|running|flash|molotov|heaven|roof|counter.strike',text.split('Markdown Content:',1)[1],re.I):
                result={'status':'insufficient_evidence','url':url,'reason':'reader_cookie_shell_only'}
            else:
                title=re.search(r'^Title: (.*)$',text,re.M)
                result={'status':'read','url':url,'title':title[1] if title else '',
                        'text':text.split('Markdown Content:',1)[1][:50000],
                        'videos':list(dict.fromkeys(canonical_url(v) for v in re.findall(r'https://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]{11}|youtu\.be/[\w-]{11})',text))),
                        'content_hash':hashlib.sha256(text.encode()).hexdigest(),'scope':'Jina Reader returned text only; no frames watched'}
        except ResearchStop:raise
        except Exception as exc:result={'status':'inaccessible','reason':type(exc).__name__,'url':url}
        result.update(observed_at=now(),provider='agent_reach/jina_reader')
        self.budget.event('read','https://r.jina.ai/'+url,result['status'])
        return self.sources._store(path,result)
