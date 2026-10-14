"""Player hub, stats and tactic room. All network calls go through mock transports (no Steam traffic)."""
import json,time
import httpx,pytest
from cs2_agent import player_hub as hub,player_stats as ps,tactic_room as room,demo_review as dr

@pytest.fixture
def home(tmp_path,monkeypatch):
    for k,v in {'BASE':tmp_path/'account','ACCOUNT':tmp_path/'account/account.json','SECRETS':tmp_path/'account/secrets.json','SETTINGS':tmp_path/'account/settings.json',
                'IMPORTS':tmp_path/'account/imports.json','CODES':tmp_path/'account/codes.json'}.items():monkeypatch.setattr(hub,k,v)
    hub.PENDING.clear();return tmp_path

def encode(match_id,outcome_id,token):
    b=int(match_id).to_bytes(8,'little')+int(outcome_id).to_bytes(8,'little')+int(token).to_bytes(2,'little')
    n=int.from_bytes(b[::-1],'big');out=''
    for _ in range(25):out+=hub.ALPHABET[n%57];n//=57
    return 'CSGO-'+'-'.join(out[i:i+5] for i in range(0,25,5))

def test_sharecode_round_trip():
    code=encode(3230642215713767580,3230647245200211980,55788)
    assert hub.decode_sharecode(code)=={'match_id':'3230642215713767580','outcome_id':'3230647245200211980','token':55788}

def test_steamid_validation_and_secrets_never_returned(home):
    with pytest.raises(ValueError):hub.valid_steamid('123')
    assert hub.valid_steamid('https://steamcommunity.com/profiles/76561198113666193/')=='76561198113666193'
    hub.save_settings({'api_key':'A'*32,'auth_code':'AAAA-AAAAA-AAAA'})
    acc=hub.account();assert acc['has_api_key'] and acc['has_auth_code'] and 'A'*32 not in json.dumps(acc)
    with pytest.raises(ValueError):hub.save_settings({'api_key':'not-a-key'})

def openid_params(state,sid='76561198113666193',return_to=None):
    rt=return_to or f'{hub.ORIGIN}/auth/steam/return?state={state}'
    return {'state':[state],'openid.mode':['id_res'],'openid.return_to':[rt],'openid.claimed_id':[f'https://steamcommunity.com/openid/id/{sid}'],'openid.sig':['x']}

def test_openid_requires_steam_confirmation_and_single_use_state(home):
    ok=httpx.MockTransport(lambda r:httpx.Response(200,text='ns:http://specs.openid.net/auth/2.0\nis_valid:true\n'))
    bad=httpx.MockTransport(lambda r:httpx.Response(200,text='is_valid:false\n'))
    url=hub.openid_start();state=url.split('state%3D')[1].split('&')[0]
    with pytest.raises(ValueError):hub.openid_return(openid_params(state),transport=bad)
    url=hub.openid_start();state=url.split('state%3D')[1].split('&')[0]
    assert hub.openid_return(openid_params(state),transport=ok)=='76561198113666193'
    assert hub.account()['verified'] is True and hub.account()['via']=='steam_openid'
    with pytest.raises(ValueError):hub.openid_return(openid_params(state),transport=ok)   # state is single-use
    with pytest.raises(ValueError):hub.openid_return(openid_params('forged'),transport=ok)
    url=hub.openid_start();state=url.split('state%3D')[1].split('&')[0]
    with pytest.raises(ValueError):hub.openid_return(openid_params(state,return_to='https://evil.example/'),transport=ok)

def rnd(events,hp_end):
    players={'P1':{'side':'T','hp':[100,hp_end['P1']]},'P2':{'side':'T','hp':[100,hp_end['P2']]},'P6':{'side':'CT','hp':[100,hp_end['P6']]},'P7':{'side':'CT','hp':[100,hp_end['P7']]}}
    return {'number':1,'players':players,'events':events}

def test_round_stats_adr_cap_trade_and_rating():
    ev=[{'k':'player_hurt','t':1,'a':'P6','by':'P1','d':112,'h':0,'w':'ak47'},           # capped to 100
        {'k':'player_death','t':1,'a':'P6','by':'P1','as':'P2','hs':True},
        {'k':'player_hurt','t':2,'a':'P1','by':'P2','d':30,'h':70,'w':'ak47'},           # team damage: ignored
        {'k':'player_death','t':3,'a':'P1','by':'P7'},
        {'k':'player_death','t':5,'a':'P7','by':'P2'}]                                  # P2 trades P1 within 5 s
    acc={};ps.round_stats(rnd(ev,{'P1':0,'P2':100,'P6':0,'P7':0}),acc,{'P1':'one'})
    p1,p2=ps.finish(acc['P1']),ps.finish(acc['P2'])
    assert p1['damage']==100 and p1['kills']==1 and p1['headshots']==1 and p1['opening_kills']==1 and p1['traded']==1 and p1['kast']==100
    assert p2['damage']==0 and p2['assists']==1 and p2['kills']==1 and p2['survived']==1
    assert acc['P6']['opening_deaths']==1 and acc['P6']['traded']==1 and acc['P6']['kast_rounds']==1  # P7 avenged P6 within 5 s
    assert p1['rating1']>0 and 'rating2_approx' in p1 and p1['name']=='one'

def test_tactic_room_crud(tmp_path,monkeypatch):
    monkeypatch.setattr(room,'BASE',tmp_path/'room')
    step={'players':[{'id':'T1','side':'T','position':[0,0,0]}],'items':[{'type':'smoke','pts':[[10,10]],'color':'#fff'}],'lines':[],'note':''}
    t=room.save({'name':'A 大爆弹','map':'de_dust2','tags':['默认','A'],'folder':'进攻','steps':[step]})
    assert t['stages']==1 and t['items']==1
    t2=room.save({'id':t['id'],'name':'A 大爆弹 v2','map':'de_dust2','tags':['A'],'steps':[step,step]})
    assert t2['id']==t['id'] and t2['stages']==2 and room.get(t['id'])['created']<=room.get(t['id'])['updated']
    d=room.duplicate(t['id']);lst=room.listing('de_dust2')
    assert len(lst['tactics'])==2 and 'A' in lst['tags'] and lst['folders']==['进攻']
    assert room.listing('de_nuke')['tactics']==[] and len(room.listing(q='v2')['tactics'])==2
    room.delete(d['id']);assert len(room.listing()['tactics'])==1
    with pytest.raises(ValueError):room.save({'name':'x','map':'de_cache_old','steps':[step]})
    with pytest.raises(ValueError):room.get('../../etc')

def test_import_local_rejects_non_demo(tmp_path):
    f=tmp_path/'x.dem';f.write_bytes(b'NOTADEMO')
    with pytest.raises(ValueError):dr.import_local(f)
    with pytest.raises(ValueError):dr.import_local(tmp_path/'missing.dem')

def test_stage_duration_validated():
    step={'players':[],'items':[],'lines':[],'note':'','dur':3}
    assert dr.validate_steps([step])
    for bad in (0.1,99,'3'):
        with pytest.raises(ValueError):dr.validate_steps([{**step,'dur':bad}])

def test_board_items_can_carry_a_floor():
    step={'players':[],'items':[{'type':'smoke','pts':[[1,1]],'color':'#fff','floor':'lower'}],'lines':[],'note':''}
    assert dr.validate_steps([step])
    with pytest.raises(ValueError):dr.validate_steps([{**step,'items':[{'type':'smoke','pts':[[1,1]],'floor':'basement'}]}])

def test_agent_prompts_follow_ui_language():
    from cs2_agent import demo_coach
    assert 'English' in demo_coach.LANG_PROMPT('en','用中文直接判断') and '用中文' not in demo_coach.LANG_PROMPT('en','用中文直接判断')
    assert demo_coach.LANG_PROMPT('zh','用中文直接判断')=='用中文直接判断'
