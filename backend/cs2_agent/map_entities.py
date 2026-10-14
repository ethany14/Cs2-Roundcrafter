"""Classify map entities from Source2Viewer's decompiled entity dump.

Map configuration identifies a door, but never establishes its demo-time pose.
"""
import hashlib
import json
import re
from collections import Counter
from .casebook import ROOT


# Only classes confirmed in the locally exported maps belong in this registry.
DYNAMIC_DOOR_CLASSES = {'prop_door_rotating'}


def parse_entities(text):
    entities = []
    for match in re.finditer(r'^====(\d+)====\s*\n(.*?)(?=^====\d+====|\Z)', text, re.M | re.S):
        fields = {}
        for line in match[2].splitlines():
            field = re.match(r'^(\S+)\s+(.+?)\s*$', line)
            if not field:
                continue
            key, value = field.groups()
            if value.startswith('resource_name:'):
                value = value[len('resource_name:'):]
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                pass
            fields[key] = value
        entities.append({'dump_index': int(match[1]), **fields})
    return entities


def classify(entity):
    classname = entity.get('classname', '')
    if classname in DYNAMIC_DOOR_CLASSES:
        return 'dynamic_door'
    # An unfamiliar class is an inspection candidate, never inferred from art.
    if 'door' in classname.lower():
        return 'unverified_door_class'
    return 'other'


def inspect_dump(path, map_name):
    entities = parse_entities(path.read_text(encoding='utf-8'))
    fields = ('dump_index', 'classname', 'targetname', 'hammeruniqueid', 'model',
              'origin', 'angles', 'spawnpos', 'distance', 'speed', 'forceclosed',
              'spawnflags', 'opendir', 'parentname')
    doors = [{**{key: e[key] for key in fields if key in e},
              'runtime_state': 'unknown_requires_demo_entity_updates',
              'configuration_is_runtime_evidence': False}
             for e in entities if classify(e) == 'dynamic_door']
    return {'map': map_name, 'source': str(path.relative_to(ROOT)),
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'entity_count': len(entities), 'class_counts': dict(Counter(e.get('classname', '<missing>') for e in entities)),
            'dynamic_doors': doors,
            'unverified_door_classes': sorted({e['classname'] for e in entities if classify(e) == 'unverified_door_class'}),
            'scope': 'exported entity lump only; not a reconstruction of runtime states'}


def main():
    paths = [('de_dust2', 'current-entities/maps/de_dust2/entities/default_ents.vents'),
             ('de_nuke', 'nuke-entities/maps/de_nuke/entities/default_ents.vents')]
    results = [inspect_dump(ROOT / 'data/maps' / path, name) for name, path in paths]
    output = ROOT / 'outputs/casebook/map-entity-comparison.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([{'map': r['map'], 'entities': r['entity_count'],
                       'dynamic_doors': len(r['dynamic_doors']),
                       'unverified': r['unverified_door_classes']} for r in results]))


if __name__ == '__main__':
    main()
