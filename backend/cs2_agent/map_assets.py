"""Import locally exported Source 2 collision geometry and semantic model tags."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .casebook import ROOT
from .geometry import Mesh


def gltf_triangles(path):
    d=json.loads(path.read_text(encoding='utf-8'))
    buffers=[(path.parent/b['uri']).read_bytes() for b in d['buffers']]
    def accessor(index):
        a=d['accessors'][index];v=d['bufferViews'][a['bufferView']]
        if 'sparse' in a:raise ValueError('Sparse glTF accessor not supported')
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        offset=v.get('byteOffset',0)+a.get('byteOffset',0)
        return np.ndarray((a['count'],width),dtype=dtype,buffer=buffers[v['buffer']],offset=offset,
                          strides=(v.get('byteStride',width*dtype.itemsize),dtype.itemsize)).copy()
    output=[]
    def visit(index,parent):
        n=d['nodes'][index]
        if 'rotation' in n:raise ValueError('Quaternion node transform requires explicit conversion')
        local=np.asarray(n.get('matrix',np.eye(4).flatten(order='F')),float).reshape(4,4,order='F')
        if 'translation' in n:local[:3,3]=n['translation']
        if 'scale' in n:local[:3,:3]=local[:3,:3]@np.diag(n['scale'])
        transform=parent@local
        if 'mesh' in n:
            for primitive in d['meshes'][n['mesh']]['primitives']:
                if primitive.get('mode',4)!=4:continue
                positions=accessor(primitive['attributes']['POSITION'])
                points=np.c_[positions,np.ones(len(positions))]@transform.T
                # glTF Y-up metres -> game Z-up units.
                points=points[:,[2,0,1]]/.0254
                indices=accessor(primitive['indices']).reshape(-1,3)
                output.append((points[indices],{'name':n.get('name',path.stem),**n.get('extras',{})}))
        for child in n.get('children',[]):visit(child,transform)
    for node in d['scenes'][d.get('scene',0)]['nodes']:visit(node,np.eye(4))
    return output


def build():
    directory=ROOT/'data/maps';groups=[];triangles=[];indices=[];ignored=[]
    path=directory/'current-physics_physics.gltf'
    for tris,metadata in gltf_triangles(path):
        tags=metadata.get('InteractAs',[])
        # Invisible collision helpers must not become visual or bullet walls.
        if set(tags)&{'playerclip','npcclip','csgo_grenadeclip','sky'}:
            ignored.append({'metadata':metadata,'triangles':len(tris)});continue
        group=len(groups);groups.append(metadata);triangles.append(tris);indices.extend([group]*len(tris))
    door_tri=[];door_groups=[];door_indices=[]
    for door in sorted((directory/'current-doors').rglob('*.gltf')):
        if 'dust_door_' not in door.name or door.stem.endswith('_physics'):continue
        for tris,meta in gltf_triangles(door):
            door_indices.extend([len(door_groups)]*len(tris));door_groups.append({'asset':door.name,**meta});door_tri.append(tris)
    ladder=directory/'ladder-merged.gltf'
    ladder_tri=np.concatenate([t for t,_ in gltf_triangles(ladder)]) if ladder.exists() else np.empty((0,3,3))
    np.savez_compressed(directory/'current-scene.npz',triangles=np.concatenate(triangles).astype('float32'),
                        groups=np.asarray(indices,dtype='int32'),door_triangles=np.concatenate(door_tri).astype('float32'),
                        door_groups=np.asarray(door_indices,dtype='int32'),ladder_triangles=ladder_tri.astype('float32'))
    entities=(directory/'current-entities/maps/de_dust2/entities/default_ents.vents').read_text(encoding='utf-8')
    import re
    dynamic=[m for m in re.findall(r'classname\s+"([^"]+)"',entities) if 'door' in m or 'ladder' in m or 'breakable' in m]
    metadata={'source':'local installed CS2 de_dust2.vpk; exported by Source2Viewer-CLI 20.0',
              'import_date':'2026-10-13','map_policy':'current installed map assumed applicable to recent matches; not exact historical reconstruction',
              'groups':groups,'door_groups':door_groups,'excluded_helper_groups':ignored,
              'dynamic_entity_classes':dynamic,'collision_triangles':sum(map(len,triangles)),
              'door_triangles':sum(map(len,door_tri)),'ladder_visual_triangles':len(ladder_tri),
              'physics_resource_sha256':hashlib.sha256((directory/'world_physics.vmdl_c').read_bytes()).hexdigest(),
              'scene_sha256':hashlib.sha256((directory/'current-scene.npz').read_bytes()).hexdigest()}
    (directory/'current-scene.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in metadata.items() if k not in ('groups','door_groups','excluded_helper_groups')},ensure_ascii=False))


def load_scene():
    directory=ROOT/'data/maps'
    path=directory/'current-scene.npz'
    if not path.exists():return Mesh.from_obj(directory/'de_dust2.obj')
    metadata=json.loads((directory/'current-scene.json').read_text(encoding='utf-8'))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['scene_sha256']:raise ValueError('Scene checksum mismatch')
    with np.load(path,allow_pickle=False) as data:
        mesh=Mesh(data['triangles']);mesh.surface_ids=data['groups'].copy();mesh.surfaces=metadata['groups']
        mesh.doors=Mesh(data['door_triangles']);mesh.doors.surface_ids=data['door_groups'].copy();mesh.doors.surfaces=metadata['door_groups']
        mesh.ladder_bounds=(data['ladder_triangles'].min(axis=1),data['ladder_triangles'].max(axis=1)) if len(data['ladder_triangles']) else None
    mesh.sha256=metadata['scene_sha256'];mesh.asset_provenance=metadata
    if (directory/'convex-solids.npz').exists():
        from .solid_geometry import Solids
        mesh.solids=Solids()
    return mesh


if __name__=='__main__':build()
