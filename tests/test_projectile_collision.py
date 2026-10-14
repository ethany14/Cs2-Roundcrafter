import numpy as np
from cs2_agent.geometry import Mesh
from cs2_agent.projectile_collision import sweep,advance

def plane():return Mesh([[[-100,-100,0],[100,-100,0],[100,100,0]],[[-100,-100,0],[100,100,0],[-100,100,0]]])
def test_radius_stops_before_surface():
 h=sweep(plane(),[0,0,10],[0,0,-10],2);assert abs(h['fraction']-.4)<1e-8;assert np.allclose(h['normal'],[0,0,1])
def test_reverse_face():
 h=sweep(plane(),[0,0,-10],[0,0,10],2);assert abs(h['fraction']-.4)<1e-8;assert h['normal'][2]<0
def test_miss():assert sweep(plane(),[200,200,10],[200,200,-10],2) is None
def test_edge_caught_without_center_ray_hit():
 m=Mesh([[[0,0,0],[10,0,0],[0,10,0]]]);h=sweep(m,[5,-1,5],[5,-1,-5],2);assert h and h['feature']=='edge';assert abs(h['fraction']-(5-np.sqrt(3))/10)<1e-8
def test_vertex():
 m=Mesh([[[0,0,0],[10,0,0],[0,10,0]]]);h=sweep(m,[-1,-1,5],[-1,-1,-5],2);assert h and h['feature']=='vertex';assert abs(h['fraction']-(5-np.sqrt(2))/10)<1e-8
def test_moving_away_from_contact():assert sweep(plane(),[0,0,2],[0,0,5],2) is None
def test_remaining_tick_is_consumed():
 x,v,h,settled,limited=advance(plane(),[0,0,3],[0,0,-100],.02,gravity=0,radius=2,elasticity=1);assert np.allclose(x,[0,0,3.01]);assert v[2]==100;assert not settled and not limited and len(h)==1
def test_free_flight():
 x,v,_,_,_=advance(plane(),[0,0,50],[10,20,30],.01);assert np.allclose(x,[.1,.2,50.284]);assert np.allclose(v,[10,20,26.8])
