import copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cs2_agent import demo_review as d
class DemoReviewTests(unittest.TestCase):
 def player(self,id,side='T',area='BombsiteA',position=None):
  return dict(id=id,side=side,area=area,position=position or [0,0,0],alive=True,inventory=['Smoke Grenade'])
 def round(self):
  return dict(number=1,start_tick=0,end_tick=6400,duration=100,frames=[dict(tick=0,seconds=0,players=[self.player('P1',area='TSpawn'),self.player('P2',area='TSpawn'),self.player('P3',area='TSpawn')]),dict(tick=640,seconds=10,players=[self.player('P1'),self.player('P2'),self.player('P3')])],events=[])
 def test_fast_entry_is_inference(self):
  c=d.analyze_round(self.round())[0];self.assertEqual(c['family'],'fast_entry');self.assertEqual(c['objective'],'A');self.assertTrue(c['unknown']);self.assertTrue(all(f['kind']=='observed' for f in c['facts']))
 def test_no_group_no_invented_intent(self):
  r=self.round();r['frames'][1]['players']=r['frames'][1]['players'][:2];self.assertEqual(d.analyze_round(r)[0]['family'],'default')
 def test_later_plant_does_not_relabel_entry(self):
  r=self.round();r['frames'].append(dict(tick=3200,seconds=50,players=[self.player('P1',area='BombsiteB')]));r['events']=[dict(id='plant',type='bomb_planted',seconds=50,tick=3200,actor='P1',side='T',position=[0,0,0])];self.assertEqual(d.analyze_round(r)[0]['objective'],'A')
 def test_empty_frames(self):
  r=self.round();r['frames']=[];self.assertEqual(d.analyze_round(r),[])
 def test_invalid_paths(self):
  for x in ['../x','a'*31,None]:
   with self.assertRaises(ValueError):d.folder(x)
 def test_upload_limits(self):
  for size in [0,7,d.MAX_BYTES+1]:
   with self.assertRaises(ValueError):d.upload(io.BytesIO(b''),size,'x.dem')
 def test_bad_magic_releases_lock(self):
  with tempfile.TemporaryDirectory() as t,patch.object(d,'BASE',Path(t)):
   with self.assertRaises(ValueError):d.upload(io.BytesIO(b'bad-demo'),8,'x.dem')
   self.assertFalse(d.LOCK.locked());self.assertEqual(d.library()[0]['status'],'failed')
 def test_board_validation_and_persistence(self):
  with tempfile.TemporaryDirectory() as t,patch.object(d,'BASE',Path(t)),patch.object(d,'result',return_value={}):
   (Path(t)/('a'*32)).mkdir()
   raw=dict(match='a'*32,name='test',steps=[dict(players=[self.player('P1')],lines=[],note='plan')]);out=d.save_board(raw);self.assertEqual(d.boards('a'*32)[0]['id'],out['id']);raw['steps'][0]['players'][0]['position']=[float('nan'),0,0]
   with self.assertRaises(ValueError):d.save_board(raw)
if __name__=='__main__':unittest.main()
