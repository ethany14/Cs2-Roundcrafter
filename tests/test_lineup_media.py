import importlib.util,json
from cs2_agent.casebook import ROOT
def module(tmp_path):
 spec=importlib.util.spec_from_file_location('lineup_media',ROOT/'experiments/knowledge/lineup_media.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.BASE=tmp_path;m.INDEX=tmp_path/'index.json';return m
def test_manifest_deduplicates_assets_preserves_source_and_methods(tmp_path):
 m=module(tmp_path);f=tmp_path/'observed.json';row={'url':'https://metastack.gg/nades/123-example','snapshot':'58 text Running\n59 text Jump Throw','dom':{'title':'Example','images':[{'src':'https://cdn.metastack.gg/x.jpg'},{'src':'https://cdn.metastack.gg/x.jpg'},{'src':'https://other.invalid/x.jpg'}],'iframes':['https://www.youtube-nocookie.com/embed/F8mjzdNhhAU']}}
 f.write_text(json.dumps([row]));m.collect(f);x=m.read()['items'][0];assert len(x['image_urls'])==1;assert x['source_tags']==['Running','Jump Throw'];assert x['video_ids']==['F8mjzdNhhAU'];assert not x['aim_verified'];assert x['publication_permission']=='not_established'
def test_rerun_keeps_download_and_review_candidates(tmp_path):
 m=module(tmp_path);f=tmp_path/'observed.json';row={'url':'https://metastack.gg/nades/123-example','verified_tags':['Standing','Jump Throw'],'snapshot':'','dom':{'title':'Example','images':[],'iframes':[]}};f.write_text(json.dumps([row]));m.collect(f);data=m.read();data['items'][0]['frames']=[{'file':'frames/a.jpg','label':'unreviewed'}];m.save(data);m.collect(f);assert m.read()['items'][0]['frames'][0]['label']=='unreviewed'
