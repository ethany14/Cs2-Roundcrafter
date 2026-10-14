"""Bounded local media collection and review-only frame extraction.

Input is rendered-page evidence exported through the user's browser. No cookies,
tokens, private endpoints or account export are used by the downloader.
"""
import argparse,hashlib,json,re,subprocess,sys,urllib.request,uuid
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[2];BASE=ROOT/'data/knowledge/metastack/media';INDEX=BASE/'index.json'
def read():return json.loads(INDEX.read_text(encoding='utf-8'))
def save(data):BASE.mkdir(parents=True,exist_ok=True);INDEX.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def collect(path):
 rows=json.loads(Path(path).read_text(encoding='utf-8'));items=[]
 old={x['id']:x for x in read()['items']} if INDEX.exists() else {}
 for row in rows:
  ident=re.search(r'/nades/(\d+)',row['url'])
  if not ident:continue
  ident=ident[1];dom=row['dom'];text=row['snapshot'];vids=[]
  for url in dom.get('iframes',[]):
   match=re.search(r'youtube(?:-nocookie)?\.com/embed/([\w-]{11})',url or '')
   if match:vids.append(match[1])
  images=list(dict.fromkeys(x['src'] for x in dom.get('images',[]) if urlparse(x['src']).hostname=='cdn.metastack.gg'))
  tags=row.get('verified_tags') or re.findall(r'\btext (Standing|Running|Walking|Crouched Walking|Crouched|Step|W \+ Jump Throw|Jump Throw|Normal Throw|Right Click Throw|Right Click Jump Throw|Left \+ Right Click Throw|Left \+ Right Click Jump Throw)\s*$',text,re.M)
  item=old.get(ident,{'id':ident,'images':[],'frames':[],'video_status':'queued'})
  item.update(title=dom.get('title'),source_url=row['url'],source_tags=list(dict.fromkeys(tags)),image_urls=images,video_ids=list(dict.fromkeys(vids)),capture_status='rendered_page_observed',image_order='DOM preload order, not instructional order',publication_permission='not_established',aim_verified=False)
  items.append(item)
 save({'schema':1,'tactic_id':'metastack-64994','tactic_source':'https://metastack.gg/strats/64994-gl-a-fake-to-ramp-pop-forcebuy','items':items,'notice':'本地研究素材；清晰截图不等于正确瞄点。保留来源，发布权限尚未确认。'})
 print(json.dumps({'items':len(items),'image_urls':sum(len(x['image_urls']) for x in items),'video_ids':sum(len(x['video_ids']) for x in items)}))
def download_images():
 from PIL import Image
 data=read()
 for item in data['items']:
  existing={x['url'] for x in item['images']}
  for url in item['image_urls']:
   if url in existing:continue
   name=hashlib.sha256(url.encode()).hexdigest()[:20]+'.jpg';dest=BASE/'assets'/name;dest.parent.mkdir(parents=True,exist_ok=True)
   try:
    with urllib.request.urlopen(url,timeout=25) as r:
     if urlparse(r.url).hostname!='cdn.metastack.gg':raise ValueError('Unexpected redirect')
     b=r.read(20*1024*1024+1)
    if len(b)>20*1024*1024:raise ValueError('Image too large')
    dest.write_bytes(b)
    with Image.open(dest) as im:width,height=im.size;im.verify()
    item['images'].append(dict(url=url,file='assets/'+name,width=width,height=height,sha256=hashlib.sha256(b).hexdigest(),label='unreviewed'))
   except Exception as e:item.setdefault('errors',[]).append({'kind':'image','url':url,'error':type(e).__name__})
   save(data)
  print(item['id']+' images '+str(len(item['images'])),flush=True)
def download_videos(limit):
 import imageio_ffmpeg
 data=read();count=0
 for item in data['items']:
  if count>=limit:break
  if item.get('video_file') or not item['video_ids']:continue
  count+=1;vid=item['video_ids'][0];out=BASE/'videos'/item['id'];out.parent.mkdir(parents=True,exist_ok=True)
  cmd=[sys.executable,'-m','yt_dlp','--no-playlist','--no-progress','--socket-timeout','20','--retries','0','--fragment-retries','0','--max-filesize','200M','--ffmpeg-location',imageio_ffmpeg.get_ffmpeg_exe(),'-f','best[height<=1080]/bestvideo[height<=1080]+bestaudio/best','--merge-output-format','mp4','-o',str(out)+'.%(ext)s','https://www.youtube.com/watch?v='+vid]
  try:
   run=subprocess.run(cmd,capture_output=True,text=True,timeout=180,encoding='utf-8',errors='replace')
   media=[p for p in out.parent.glob(item['id']+'.*') if p.suffix in ['.mp4','.webm','.mkv']]
   if run.returncode!=0 or not media:
    item['video_status']='download_failed';item['video_error']=(run.stderr or 'No output video')[-1800:];save(data);print(item['id']+' video download failed; stopping batch',flush=True);break
   item['video_file']=str(media[0].relative_to(BASE)).replace('\\','/');item['video_status']='downloaded'
  except subprocess.TimeoutExpired:item['video_status']='timeout';save(data);break
  save(data);print(item['id']+' video downloaded',flush=True)
def frames(ident,video=None,fps=1):
 import imageio_ffmpeg
 from PIL import Image,ImageFilter,ImageStat
 data=read();item=next(x for x in data['items'] if x['id']==ident)
 path=Path(video).resolve() if video else BASE/item['video_file'];folder=BASE/'frames'/ident/uuid.uuid4().hex[:12];folder.mkdir(parents=True,exist_ok=True)
 if not path.is_file():raise ValueError('Missing local video')
 if not .1<=fps<=10:raise ValueError('fps must be 0.1–10')
 # Times are nominal output-frame times, not exact source PTS; do not infer aim.
 cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-i',str(path),'-t','180','-vf',f'fps={fps},scale=1920:1080:force_original_aspect_ratio=decrease','-frames:v','600','-q:v','2',str(folder/'frame-%05d.jpg')]
 subprocess.run(cmd,check=True,timeout=180,capture_output=True)
 files=sorted(folder.glob('frame-*.jpg'));result=[];prev=None
 for i,file in enumerate(files):
  with Image.open(file) as im:
   small=im.convert('L').resize((160,90));values=list(small.get_flattened_data());clarity=ImageStat.Stat(small.filter(ImageFilter.FIND_EDGES)).stddev[0]
   delta=None if prev is None else sum(abs(a-b) for a,b in zip(values,prev))/len(values)
   result.append(dict(file=str(file.relative_to(BASE)).replace('\\','/'),timestamp_seconds=i/fps,clarity=round(clarity,2),frame_difference=None if delta is None else round(delta,2),label='unreviewed',width=im.width,height=im.height));prev=values
 item['frames']=result;item['frame_source']={'kind':'local_video' if video else 'downloaded_source_video','video_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'fps':fps,'semantic_aim_detection':False,'max_seconds':180,'max_frames':600};save(data);print(json.dumps({'id':ident,'frames':len(result)}))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['collect','images','videos','frames']);ap.add_argument('--observed');ap.add_argument('--limit',type=int,default=1);ap.add_argument('--id');ap.add_argument('--video');ap.add_argument('--fps',type=float,default=1);a=ap.parse_args()
 if a.mode=='collect':collect(a.observed)
 elif a.mode=='images':download_images()
 elif a.mode=='videos':download_videos(max(1,min(a.limit,20)))
 else:frames(a.id,a.video,a.fps)
