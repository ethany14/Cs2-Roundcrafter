import json,threading
import pytest
from cs2_agent import demo_match_coach as b, demo_coach as c

@pytest.fixture
def batch(tmp_path,monkeypatch):
 mid='a'*32;root=tmp_path/mid;root.mkdir()
 monkeypatch.setattr(b.dr,'folder',lambda m:root)
 monkeypatch.setattr(b.dr,'result',lambda m:{'map':'de_nuke','rounds':[{'number':n} for n in [1,2,3]]})
 monkeypatch.setattr(b,'destination',lambda:{'configured':True,'host':'example.test'})
 monkeypatch.setattr(c,'LOCK',threading.Lock());monkeypatch.setattr(c,'ACTIVE',{});monkeypatch.setattr(b,'ACTIVE',{})
 monkeypatch.setattr(b,'launch',lambda target,args:target(*args))
 class FixtureSession:
  def __init__(self,mid,n,additional_calls,endpoint_host):
   self.mid=mid;self.n=n;self.used=0;self.allowance=additional_calls;self.state={};self.cancelled=threading.Event()
  def run(self):
   self.state={'model_calls':1,'status':'completed' if self.allowance>=1 else 'budget_exhausted'}
   if self.state['status']=='completed':
    self.state.update(version=c.VERSION,result={'claims':[{'observed_title':'fixture','start':1,'end':2,'players':['P1']}]})
   b.write_json(c.path(self.mid,self.n),self.state)
 monkeypatch.setattr(c,'Session',FixtureSession)
 return {'match':mid,'request_id':'b'*32,'consent':True,'endpoint_host':'example.test','max_calls':9}

def test_queue_processes_every_round_and_indexes_clips(batch):
 j=b.start(batch);assert j['completed']==[1,2,3];assert j['calls']==3;assert j['status']=='completed'
 index=b.index(batch['match']);assert len(index['claims'])==3;assert all(x['start']<x['end'] for x in index['claims'])
 assert not c.LOCK.locked()

def test_total_budget_stops_remaining_rounds(batch):
 batch['max_calls']=2;j=b.start(batch)
 assert j['calls']==2 and j['status']=='budget_exhausted';assert j['completed']==[1,2];assert j['failed']==[]

def test_same_request_does_not_spend_twice(batch):
 first=b.start(batch);second=b.start(batch);assert first==second

def test_current_results_are_reused(batch):
 b.start(batch);batch['request_id']='c'*32;j=b.start(batch);assert j['rounds']==[] and j['calls']==0

def test_explicit_regeneration_and_scope(batch):
 b.start(batch);batch.update(request_id='c'*32,rounds=[2],regenerate=True);j=b.start(batch);assert j['rounds']==[2] and j['calls']==1

@pytest.mark.parametrize('change',[{'consent':False},{'endpoint_host':'other.test'},{'max_calls':201},{'rounds':[999]},{'rounds':[1,1]}])
def test_rejects_missing_consent_wrong_destination_and_invalid_budget(batch,change):
 batch.update(change)
 with pytest.raises(ValueError):b.start(batch)
 assert not c.LOCK.locked()

def test_cancel_and_restart_never_auto_resume(batch):
 event=threading.Event();b.ACTIVE[batch['match']]=({},event)
 assert b.cancel(batch)['cancel_requested'];assert event.is_set();b.ACTIVE.clear()
 p=b.job_path(batch['match'],batch['request_id']);b.write_json(p,{'status':'running','created_at':1})
 assert b.index(batch['match'])['job']['status']=='interrupted'

def test_old_api_does_not_authorize_new_match(batch):
 with pytest.raises(ValueError):c.start({'match':batch['match'],'round':1})


def test_real_parallel_overlap_and_reserved_total(batch,monkeypatch):
 barrier=threading.Barrier(3);guard=threading.Lock();live=0;peak=0;allowances=[]
 class Parallel:
  def __init__(self,mid,n,additional_calls,endpoint_host):
   self.n=n;self.used=0;self.state={'model_calls':0};self.allowance=additional_calls
   with guard:allowances.append(additional_calls)
  def run(self):
   nonlocal live,peak
   with guard:live+=1;peak=max(peak,live)
   barrier.wait(timeout=3)
   self.state={'model_calls':self.allowance,'status':'completed'}
   with guard:live-=1
 monkeypatch.setattr(c,'Session',Parallel);batch.update(max_calls=5,concurrency=3)
 j=b.start(batch)
 assert peak==3 and sum(allowances)==5 and j['calls']==5
 assert j['completed']==[1,2,3] and j['reserved_calls']==0

def test_cancel_stops_waiting_rounds(batch,monkeypatch):
 seen=[]
 class Cancel:
  def __init__(self,mid,n,additional_calls,endpoint_host):self.n=n;self.used=0;self.state={'model_calls':0}
  def run(self):
   seen.append(self.n);self.cancelled.set();self.state={'model_calls':1,'status':'cancelled'}
 monkeypatch.setattr(c,'Session',Cancel);batch['concurrency']=1
 j=b.start(batch);assert seen==[1] and j['status']=='cancelled' and j['calls']==1

@pytest.mark.parametrize('concurrency',[0,5,True])
def test_invalid_concurrency_rejected(batch,concurrency):
 batch['concurrency']=concurrency
 with pytest.raises(ValueError):b.start(batch)
