import base64
import struct
import pytest
from cs2_agent.smoke_voxels import decode,raycast
from cs2_agent.smoke import assess


def seed_frame():
    payload=bytes([0,3,1,16,16,16,5,0,0,0,0,0,0,0])
    return struct.pack('<HH',0,len(payload))+payload


def test_keyframe_and_grid_ray_are_not_cylinder():
    data=seed_frame();cells,info=decode(data)
    assert cells.tolist()==[[16,16,16]]
    frame={'tick':10,'position':[100,100,100],'data_base64':base64.b64encode(data).decode()}
    result=raycast(frame,[90,106,106],[120,106,106])
    assert result['intersects'] and result['path_units']==pytest.approx(12)
    assert not raycast(frame,[90,130,106],[120,130,106])['intersects']
    assert not raycast(frame,[106,106,106],[106,106,106])['path_units']


def test_incomplete_and_unknown_streams_fail_closed():
    with pytest.raises(ValueError):decode(seed_frame()[:-1])
    with pytest.raises(ValueError):decode(struct.pack('<HH',0,3)+bytes([0,99,0]))
    with pytest.raises(ValueError):decode(struct.pack('<HH',0,5)+bytes([0,2,0,0,0]))


def test_future_voxel_frame_does_not_leak():
    frame={'tick':11,'position':[0,0,0],'data_base64':base64.b64encode(seed_frame()).decode()}
    smokes=[{'start_tick':1,'position':[0,0,0],'voxel_frame':frame}]
    assert not assess([-10,6,6],[20,6,6],smokes,10)['network_occupancy_available']
    assert assess([-10,6,6],[20,6,6],smokes,11)['network_voxel_evidence'][0]['intersects']
