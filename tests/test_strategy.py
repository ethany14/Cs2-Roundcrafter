from cs2_agent.strategy import candidates
def data():return dict(kit=1,kit_known=1,bomb_age=.5,bomb_distance_lower_bound=.2,ct_alive=.4,t_alive=.6,mate_nearest=.1,mates_near_bomb=.25,equipment=.4,seen_age=.1,seen_valid=0)
def test_unknown_enemy_is_not_resolved_and_no_optimality_claim():
 r=candidates(data());assert r['recommended_candidate'] is None and not r['ready_for_player_advice'];assert r['evidence']['last_seen_age_seconds'] is None
 assert len(r['candidates'])==3 and all(c['conditions'] and c['response_checks'] for c in r['candidates'])
def test_timing_is_explicit_assumption():
 r=candidates(data());assert r['scenario']['nominal_bomb_seconds_remaining']==20;assert r['scenario']['defuse_seconds_assumption']==5
 f=data();f['kit']=0;f['kit_known']=0;r=candidates(f);assert not r['scenario']['defuse_kit_known'] and r['scenario']['defuse_seconds_assumption']==10
