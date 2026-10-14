"""Website movement-prediction path: feature parity, explicit input errors, no future leakage."""
import json,math
import numpy as np
import pytest
from cs2_agent import movement_model as mm

def row(sid,team=2,x=0.0,y=0.0,z=0.0,yaw=0.0,alive=True,**kw):
    r={'steamid':sid,'X':x,'Y':y,'Z':z,'yaw':yaw,'pitch':5.0,'team_num':team,'is_alive':alive,'health':100,'armor_value':100,'duck_amount':0.0,'flash_duration':0.0,'total_rounds_played':3}
    r.update(kw);return r

def lobby(t,offset=0.0):
    return [row(f'T{i}',2,x=100*i+offset*(i==0)) for i in range(5)]+[row(f'C{i}',3,x=-1000-100*i) for i in range(5)]

def history(step=20.0):
    return [row('T0',2,x=-4*step+i*step,yaw=0.0) for i in range(5)]

def test_features_follow_training_encoding():
    h,c=mm.features(history(),lobby(0),start=0,tick=640,plants=[])
    assert np.shape(h)==(5,8) and len(c)==16
    assert h[-1][:3]==[0.0,0.0,0.0] and h[0][0]==pytest.approx(-80/250,abs=1e-3)   # yaw 0: forward = +X
    assert c[:8]==[1.0,1.0,0,0.083,1.0,1.0,0,0] and c[11]==1 and c[15]==1        # two teammates present
    assert all(v==round(v,3) for v in c)

@pytest.mark.parametrize('mutate,code',[
    (lambda h,n:h.__setitem__(1,None),'history_missing'),
    (lambda h,n:h[2].__setitem__('is_alive',False),'not_alive'),
    (lambda h,n:h[3].__setitem__('pitch',None),'field_missing'),
    (lambda h,n:h[3].__setitem__('X',900.0),'teleport'),
    (lambda h,n:n.pop(),'not_ten_players'),
    (lambda h,n:h[0].__setitem__('total_rounds_played',2),'history_crosses_round')])
def test_missing_inputs_are_rejected_not_zero_filled(mutate,code):
    h,n=history(),lobby(0);mutate(h,n)
    with pytest.raises(mm.MovementInputError) as e:mm.features(h,n,start=0,tick=640,plants=[])
    assert e.value.code==code

def test_local_world_round_trip():
    yaw=37.0;a=math.radians(yaw);dx,dy=120.0,-45.0
    loc=mm._local(dx,dy,math.cos(a),math.sin(a));(x,y),=mm.to_world([loc],[10,20],yaw)
    assert (x,y)==pytest.approx((10+dx,20+dy))

needs_model=pytest.mark.skipif(bool(mm.available()),reason='movement checkpoints or torch not installed')

@needs_model
def test_future_track_never_reaches_the_model(monkeypatch):
    span={'start':1000,'end':9000,'plants':[]};tick=1000+40*32
    def fake_rows(future_shift):
        rows={}
        for k in range(-4,5):
            t=tick+k*32;rows[str(t)]=[r|{'X':r['X']+(future_shift if k>0 and r['steamid']=='T0' else 0)+(20*k if r['steamid']=='T0' else 0)} for r in lobby(0)]
        return rows
    for shift,store in ((0,[]),(500,[])):
        rows=fake_rows(shift)
        monkeypatch.setattr(mm,'_node',lambda mode,demo,ticks='':{'rows':{t:rows[t] for t in ticks.split(',')}})
        monkeypatch.setattr(mm,'rounds',lambda mid:{'map':'de_dust2','rate':64,'rounds':[span]})
        monkeypatch.setattr(mm,'steamids',lambda mid:{'P1':'T0'})
        monkeypatch.setattr(mm,'_demo',lambda mid:'x.dem')
        monkeypatch.setattr(mm,'training_split',lambda mid:'not_in_dataset')
        import cs2_agent.demo_workbench as wb
        monkeypatch.setattr(wb,'replay_round',lambda mid,n:{'start_tick':1000})
        out=mm.predict('0'*32,1,20.0,'P1');store.append(out)
        if shift==0:base=out
    assert out['predicted']==base['predicted'] and out['inputs']==base['inputs']
    assert out['actual']['track']!=base['actual']['track']

@needs_model
def test_unsupported_map_and_early_time(monkeypatch):
    import cs2_agent.demo_workbench as wb
    monkeypatch.setattr(wb,'replay_round',lambda mid,n:{'start_tick':1000})
    monkeypatch.setattr(mm,'rounds',lambda mid:{'map':'de_vertigo','rate':64,'rounds':[{'start':1000,'end':5000,'plants':[]}]})
    with pytest.raises(mm.MovementInputError) as e:mm.predict('0'*32,1,10,'P1')
    assert e.value.code=='unsupported_map'
    monkeypatch.setattr(mm,'rounds',lambda mid:{'map':'de_nuke','rate':64,'rounds':[{'start':1000,'end':5000,'plants':[]}]})
    with pytest.raises(mm.MovementInputError) as e:mm.predict('0'*32,1,1.0,'P1')
    assert e.value.code=='insufficient_history'

@needs_model
def test_matches_stored_test_predictions():
    """The ensemble used by the site reproduces the experiment's saved test predictions."""
    d=np.load(mm.MODEL_DIR/'data.npz');tp=np.load(mm.MODEL_DIR/'test-predictions.npz');te=d['split']=='test'
    pred=mm.predict_local(d['h'][te][:64],d['c'][te][:64])
    assert np.abs(pred-tp['numeric'][:64]).max()*250<0.5
