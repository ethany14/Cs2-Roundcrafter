from cs2_agent.door_timeline import at_tick


def test_future_opening_delete_and_reused_index():
    events=[{'tick':1,'kind':'door','entity':'Index = 1, Serial = 1','pose':{'state':'closed'}},
            {'tick':20,'kind':'door','entity':'Index = 1, Serial = 1','pose':{'state':'opening'}},
            {'tick':30,'kind':'door_delete','entity':'Index = 1, Serial = 1'},
            {'tick':40,'kind':'door','entity':'Index = 1, Serial = 2','pose':{'state':'closed'}}]
    assert at_tick(events,19)[0]['pose']['state']=='closed'
    assert at_tick(events,20)[0]['pose']['state']=='opening'
    assert at_tick(events,30)==[]
    assert at_tick(events,40)[0]['entity'].endswith('Serial = 2')


def test_door_collision_follows_observed_rotation():
    from cs2_agent.door_timeline import posed_mesh
    panel=[[[0,0,0],[10,0,0],[10,0,10]],[[0,0,0],[10,0,10],[0,0,10]]]
    closed=posed_mesh(panel,{'rotation':[0,0,0],'origin':[100,100,0]})
    opened=posed_mesh(panel,{'rotation':[0,90,0],'origin':[100,100,0]})
    assert closed.blocked([105,95,5],[105,105,5])
    assert not opened.blocked([105,95,5],[105,105,5])
