"""Local installed-game radar textures and official overview transforms."""
import hashlib
import re
import struct
from PIL import Image
from .casebook import ROOT
from .free_lab import MAPS

BASE=ROOT/'data/maps/radar'

def available():
    """Maps whose radar texture and overview transform are installed. Independent of the utility lab's
    collision data, so a replay still gets its radar on machines without it."""
    return [m for m in MAPS if (BASE/'resource/overviews'/(m+'.txt')).exists()
            and (BASE/'panorama/images/overheadmaps'/(m+'_radar_psd.png')).exists()]

def metadata(name):
    if name not in available():raise ValueError('Unsupported radar map')
    overview=BASE/'resource/overviews'/(name+'.txt')
    text=overview.read_text(encoding='utf-8')
    def number(key,default=None):
        found=re.search(r'"'+re.escape(key)+r'"\s+"([\d.+-]+)"',text)
        return float(found[1]) if found else default
    image=BASE/'panorama/images/overheadmaps'/(name+'_radar_psd.png')
    raw=image.read_bytes();width,height=struct.unpack('>II',raw[16:24])
    with Image.open(image) as im:
        alpha=im.convert('RGBA').getchannel('A');box=alpha.crop((4,4,width-4,height-4)).getbbox()
        content=[(box[0]+4)/width,(box[1]+4)/height,(box[2]+4)/width,(box[3]+4)/height] if box else [0,0,1,1]
    lower=BASE/'panorama/images/overheadmaps'/(name+'_lower_radar_psd.png')
    # Shipped overhead PNG is already north-up: Dust2 bomb A (.80,.16)
    # and B (.21,.12) agree with its pixels without rotating the texture.
    return {'map':name,'pos_x':number('pos_x'),'pos_y':number('pos_y'),'scale':number('scale'),
            'overview_rotate':number('rotate',0),'content_bounds':content,'reference_size':1024,'width':width,'height':height,
            'upper_url':'/radar/'+name+'.png','lower_url':'/radar/'+name+'_lower.png' if lower.exists() else None,
            'floor_split_z':number('AltitudeMin') if lower.exists() else None,
            'insets':{k:number('inset_'+k,0) for k in ['left','right','top','bottom']},
            'landmarks':{k:[number(k+'_x'),number(k+'_y')] for k in ['CTSpawn','TSpawn','bombA','bombB'] if number(k+'_x') is not None},
            'source':'local installed CS2 pak01_dir.vpk; panorama/images/overheadmaps + resource/overviews',
            'image_sha256':hashlib.sha256(raw).hexdigest(),'overview_sha256':hashlib.sha256(overview.read_bytes()).hexdigest(),
            'formula':'u=(world_x-pos_x)/(scale*1024); v=(pos_y-world_y)/(scale*1024)',
            'height_note':'雷达仅定义 XY；高度来自相同世界坐标处的碰撞地面，不能由雷达像素猜测。'}

def image_path(name):
    base=name.removesuffix('_lower')
    if base not in available() or name not in {base,base+'_lower'}:raise ValueError('Unknown radar')
    path=BASE/'panorama/images/overheadmaps'/(name+'_radar_psd.png')
    if not path.exists():raise ValueError('Radar not available')
    return path

def world_to_uv(meta,point):
    span=meta['scale']*1024
    return [(point[0]-meta['pos_x'])/span,(meta['pos_y']-point[1])/span]

def uv_to_world(meta,uv):
    span=meta['scale']*1024
    return [meta['pos_x']+uv[0]*span,meta['pos_y']-uv[1]*span]
