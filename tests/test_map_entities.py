from cs2_agent.map_entities import parse_entities, classify, inspect_dump
from cs2_agent.casebook import ROOT


def test_model_name_never_establishes_a_dynamic_door():
    assert classify({'classname': 'prop_static', 'model': 'metal_door.vmdl'}) == 'other'
    assert classify({'classname': 'prop_door_rotating', 'model': 'plain.vmdl'}) == 'dynamic_door'
    assert classify({'classname': 'unknown_door'}) == 'unverified_door_class'


def test_map_initial_configuration_is_not_runtime_state():
    text = '====0====\nclassname "prop_door_rotating"\nspawnpos "0"\nforceclosed true\norigin [ 1.0, 2.0, 3.0 ]\nmodel resource_name:"door.vmdl"\n====1====\nclassname "prop_static"\n'
    rows = parse_entities(text)
    assert len(rows) == 2
    assert rows[0]['origin'] == [1, 2, 3]
    assert rows[0]['forceclosed'] is True
    assert rows[0]['spawnpos'] == '0'
    assert rows[0]['model'] == 'door.vmdl'
    assert 'runtime_state' not in rows[0]


def test_local_map_entity_contrast():
    import pytest
    paths = [ROOT/'data/maps/current-entities/maps/de_dust2/entities/default_ents.vents',
             ROOT/'data/maps/nuke-entities/maps/de_nuke/entities/default_ents.vents']
    if not all(p.exists() for p in paths):
        pytest.skip('Local game exports are not shipped with the source')
    dust, nuke = [inspect_dump(p, name) for p, name in zip(paths, ['de_dust2', 'de_nuke'])]
    assert not dust['dynamic_doors']
    assert len(nuke['dynamic_doors']) == 4
    assert all(not e['configuration_is_runtime_evidence'] for e in nuke['dynamic_doors'])
