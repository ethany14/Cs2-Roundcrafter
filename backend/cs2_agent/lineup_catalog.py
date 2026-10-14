"""Evidence-bearing teaching records; experiments remain in their original files."""
from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
import hashlib
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .casebook import ROOT

CATALOG = ROOT / 'data/knowledge/lineups/nuke.json'

def now():
    return datetime.now(UTC).isoformat()

def canonical_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('Only public HTTPS source URLs are supported')
    host = p.hostname.lower().removeprefix('www.')
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'fbclid','gclid'}]
    if host in {'youtube.com','youtube-nocookie.com','youtu.be'}:
        vid = dict(query).get('v') if host == 'youtube.com' and p.path == '/watch' else p.path.split('/')[-1]
        if re.fullmatch(r'[\w-]{11}', vid or ''):
            return 'https://www.youtube.com/watch?v=' + vid
    return urlunsplit(('https',host,p.path.rstrip('/') or '/',urlencode(sorted(query)),''))

@dataclass
class Evidence:
    id: str
    source_url: str
    field: str
    value: object
    quote: str
    method: str
    observed_at: str
    content_hash: str
    classification: str = 'source_fact'
    scope: str = 'metadata_only'
    video_time: float | None = None
    contradictions: list = field(default_factory=list)

@dataclass
class LineupCard:
    id: str
    title: str
    map: str | None
    kind: str | None
    source_url: str
    side: str | None = None
    origin: list = field(default_factory=list)
    target: list = field(default_factory=list)
    motion: str | None = None
    throw: str | None = None
    steps: list = field(default_factory=list)
    coordinates: object = None
    video_url: str | None = None
    participants: int | None = None
    map_version: str | None = None
    published_at: str | None = None
    source_status: str = 'historical_metadata'
    game_validation: str = 'unverified'
    evidence: list = field(default_factory=list)
    unknown: list = field(default_factory=lambda:['精确站位/瞄点','按键与释放时序','地图版本','游戏实投效果','单人配合条件'])
    legacy: dict = field(default_factory=dict)

@dataclass
class UtilityNeed:
    id: str
    map: str
    kind: str | None = None
    origin: list = field(default_factory=list)
    target: list = field(default_factory=list)
    role: str | None = None
    motion: str | None = None
    throw: str | None = None
    party_size: int = 1
    clock: float | None = None
    followup: str | None = None
    side: str = 'T'
    map_version: str | None = None
    source_url: str | None = None
    classification: str = 'product_rule'

@dataclass
class CompatibilityResult:
    need_id: str
    card_id: str
    status: str
    passed: list
    conflicts: list
    unknown: list
    rules_version: str = 'lineup-fit-1'
    game_validation: str = 'unverified'

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)

def migrate(destination=CATALOG):
    """Additive migration: all legacy lesson fields, candidates and source records survive."""
    base=ROOT/'data/knowledge/metastack'
    teaching=json.loads((base/'teaching.json').read_text(encoding='utf-8'))
    media=json.loads((base/'media-observed.json').read_text(encoding='utf-8'))
    pilot=json.loads((base/'pilot.json').read_text(encoding='utf-8'))
    tactic=next(t for t in pilot['tactics'] if t['id']=='metastack-64994')
    cards=[]
    for lesson in teaching['lessons'][:6]:
        src=next((m for m in media if m['url']==lesson['source_url']),{})
        snapshot=src.get('snapshot','')
        title=src.get('dom',{}).get('title',lesson['name'])
        tags=src.get('verified_tags',[]) + re.findall(r'\btext (Standing|Running|Crouched|Jump Throw|Normal Throw)\b',snapshot)
        motion=next((s for s in tags if s in {'Standing','Running','Crouched'}),None)
        throw=next((s for s in tags if s in {'Jump Throw','Normal Throw'}),None)
        videos=[u for u in src.get('dom',{}).get('iframes',[]) if u and 'youtube' in u]
        card=LineupCard(lesson['id'],title,'de_nuke',lesson['kind'],canonical_url(lesson['source_url']),
                        side='T',origin=lesson.get('origin',[]),target=lesson.get('destination',[]),
                        motion=motion,throw=throw,video_url=canonical_url(videos[0]) if videos else None,
                        legacy={'lesson':lesson,'source_observation':src,'parent_teaching_file':str(base/'teaching.json')})
        digest=hashlib.sha256(json.dumps(src,ensure_ascii=False).encode()).hexdigest()
        for key,value in [('title',title),('map','de_nuke'),('kind',lesson['kind']),('side','T'),('origin',card.origin),('target',card.target),('motion',motion),('throw',throw),('video_url',card.video_url)]:
            if value is None:continue
            # Area lists were a prior matching interpretation, not exact landing points.
            inferred=key in {'origin','target'}
            scope='regional_interpretation' if inferred else 'metadata_only'
            quote = json.dumps(lesson,ensure_ascii=False) if inferred else json.dumps(src,ensure_ascii=False)
            if key in {'map','kind','side'}:
                quote=json.dumps({'map':tactic['map'],'side':tactic['side'],'lesson_kind':lesson['kind'],'source_observation':src},ensure_ascii=False)
            card.evidence.append(asdict(Evidence(f"legacy-{lesson['id']}-{key}",card.source_url,key,value,quote[:14000],
                'historical_rendered_snapshot',pilot['observed_at'],digest,
                'model_inference' if inferred else 'source_fact',scope)))
        cards.append(asdict(card))
    value={'schema_version':1,'migrated_at':now(),'cards':cards,'preserved_files':['teaching.json','media-observed.json','pilot.json'],
           'note':'Historical rendered metadata, no video playback or game certification; target/origin region mapping is inference.'}
    write_json(destination,value)
    return value

def load_catalog():
    catalog=json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else migrate()
    for i,c in enumerate(catalog['cards']):
        enriched=CATALOG.parent/'enriched'/(c['id']+'.json')
        if enriched.exists() and time.time()-enriched.stat().st_mtime<7*86400:
            saved=json.loads(enriched.read_text(encoding='utf-8'))
            if saved['id']==c['id'] and saved['source_url']==c['source_url'] and saved['game_validation']=='unverified':catalog['cards'][i]=saved
    return catalog

def save_card(card):
    if not re.fullmatch(r'[0-9]+',card['id']) or card['game_validation']!='unverified' or card.get('coordinates') is not None:
        raise ValueError('Cannot save unsupported coordinates or game validation')
    write_json(CATALOG.parent/'enriched'/(card['id']+'.json'),card)

ALIASES={'天堂':'heaven','天堂烟':'heaven','天上':'heaven','屋顶':'roof','外场':'outside','过点':'cross',
         '管道':'vent','铁门':'door','匪家':'t yard','闪光':'flash','闪':'flash','烟雾':'smoke','烟':'smoke',
         '燃烧':'fire','火':'fire','三楼':'heaven','黄房':'hut','后点':'backsite'}
def words(query):
    q=query.lower()
    for a,b in ALIASES.items():q=q.replace(a,' '+b+' ')
    return set(re.findall(r'[a-z0-9]+',q)) - {'cs2','de','nuke','this','from','how','the','a','t','site'}

def retrieve_cards(query,map_name='de_nuke',cards=None):
    terms=words(query)
    requested_kind=next((k for k in ['smoke','flash','fire','he'] if k in terms),None)
    ranked=[]
    for c in cards if cards is not None else load_catalog()['cards']:
        if c['map']!=map_name:continue
        if requested_kind and c['kind']!=requested_kind:continue
        tokens=words(' '.join([c['title'],c['kind'] or '',*c['origin'],*c['target']]))
        score=len(terms & tokens)
        # Generic grenade words alone cannot select an unrelated named destination.
        destinations=terms & {'heaven','outside','cross','hut','backsite','vent','ramp','secret','garage'}
        if destinations and not destinations & tokens:continue
        if score:ranked.append((score,c))
    return [c for _,c in sorted(ranked,key=lambda r:(-r[0],r[1]['id']))][:6]

def check_fit(need,card,player=None):
    passed=[];conflicts=[];unknown=[]
    for k in ['map','side','kind','motion','throw','map_version']:
        want=need.get(k);have=card.get(k)
        if want is None:continue
        if have is None:unknown.append(k)
        elif want!=have:conflicts.append(k)
        else:passed.append(k)
    for k in ['origin','target']:
        def zone(x):
            alias={'屋顶':'roof','天堂':'heaven','三楼':'heaven','黄房顶':'hutroof','管道':'vents','匪家':'tspawn','外场':'outside'}
            return alias.get(x.lower().strip(),x.lower().strip())
        want={zone(x) for x in need.get(k) or []};have={zone(x) for x in card.get(k) or []}
        if not want:continue
        if not have:unknown.append(k)
        elif not want & have:conflicts.append(k)
        else:passed.append(k+' (regional metadata only)')
    if card.get('participants') is None:unknown.append('所需配合人数')
    elif card['participants']>need.get('party_size',1):conflicts.append('配合人数不足')
    if player is not None:
        inv=player.get('utility')
        if inv is None or card.get('kind') not in inv:unknown.append('逐人库存')
        elif inv[card['kind']]<1:conflicts.append('持有人缺少该道具')
        else:passed.append('逐人库存')
        if player.get('position_ready') is not True:unknown.append('起点可达与准备状态')
    else:unknown.append('持有人、装备和起点可达')
    unknown+=['目标枪线/楼层和效果未经实投确认','飞行与生效时间','投后路线与职责衔接','当前地图版本']
    if not card.get('steps'):unknown.append('精确瞄点和分步动作；请查看原视频')
    if any(e.get('contradictions') for e in card.get('evidence',[])):conflicts.append('来源字段冲突')
    return asdict(CompatibilityResult(need['id'],card['id'],'incompatible' if conflicts else 'unknown' if unknown else 'conditions_match',passed,conflicts,unknown))
