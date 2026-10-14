import copy
import sqlite3
import pytest
from cs2_agent.casebook import initialize, ingest, retrieve, knowledge_search, distance, import_knowledge, shortlist


def sample(identifier='q', match='test', split='test', outcome=False):
    case={'id':identifier,'demo_sha256':match,'map':'de_dust2','side':'CT','round':1,'tick':100,
          'review_status':'unreviewed','features':{'position':[0,0,0],'elapsed':40,'equipment':4000,
          'nearest_teammate':300,'own_alive':4,'enemy_alive':3,'bomb_planted':False},'outcome':outcome}
    entry={'match_id':match,'split':split,'source_url':'https://example.com/'+match,'date':'2026-01-01'}
    return {'sha256':match,'cases':[case]},entry


@pytest.fixture
def db():
    con=sqlite3.connect(':memory:');con.row_factory=sqlite3.Row;initialize(con)
    ingest(con,*sample());ingest(con,*sample('ref','reference','train'))
    yield con
    con.close()


def test_retrieval_excludes_test_and_same_match(db):
    ingest(db,*sample('other','other-test','test'))
    assert [r['id'] for r in retrieve(db,'q')['matches']]==['ref']
    assert retrieve(db,'ref')['matches']==[]


def test_split_leakage_rejected(db):
    with pytest.raises(ValueError):ingest(db,*sample('leak','reference','test'))


def test_outcome_never_changes_rank():
    a=sample()[0]['cases'][0];b=copy.deepcopy(a);b['outcome']=True
    assert distance(a,b)[0]==0


def test_mismatched_state_returns_no_match(db):
    data,entry=sample('ref','reference','train');data['cases'][0]['features']['bomb_planted']=True
    ingest(db,data,entry)
    assert retrieve(db,'q')['status']=='no_comparable_case'


def test_empty_knowledge_is_explicit(db):
    assert knowledge_search(db,'" OR smoke')==[]


def test_same_demo_cannot_cross_split(db):
    data,entry=sample('leak','new','test');data['sha256']='reference'
    with pytest.raises(ValueError):ingest(db,data,entry)


def test_unreviewed_notes_not_retrieved(db):
    note={'id':'note','kind':'tactic','map':'de_dust2','title':'support','body':'support evidence',
          'source':'https://example.com/video?t=10','version':'2026 demo version unknown','reviewed':False}
    import_knowledge(db,[note]);assert knowledge_search(db,'support')==[]
    note['reviewed']=True;import_knowledge(db,[note]);assert len(knowledge_search(db,'support'))==1


def test_clutch_not_flagged_for_missing_support(db):
    data,entry=sample();data['cases'][0]['features']['own_alive']=1
    data['cases'][0]['features']['nearest_teammate']=None
    ingest(db,data,entry);assert shortlist(db,'test')==[]
