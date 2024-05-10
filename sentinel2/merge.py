import json
from rtree import index

from shapely.ops import unary_union
from shapely.geometry import shape, mapping
from shapely.prepared import prep

max_id = 0

def idx_gen(prepared_map, all_feats):
    global max_id
    i = 0
    print('generating index')
    with open('data/clipped.geojsonl') as f:
        for line in f:
            feat = json.loads(line)
            all_feats.append(feat)
            curr_id = feat['properties']['id']
            if curr_id > max_id:
                max_id = curr_id
            s = shape(feat['geometry'])
            if not s.is_valid:
                #print('WARNING: invalid geometry for {}, fixing with buffer(0)'.format(feat['properties']))
                s = s.buffer(0)
                if not s.is_valid:
                    print('!!! ERROR !!!: invalid geometry even after buffer for {}'.format(feat['properties']))

            if len(s.bounds) == 0:
                continue
            g = prep(s)
            #g = s
            feat['geometry'] = s
            prepared_map[curr_id] = g
            #print('sending {}, {}, {}'.format(i, s.bounds, feat['properties']))
            yield (curr_id, s.bounds, curr_id)
            i += 1
            if i % 10000 == 0:
                print(f'done with {i} entries')



prepared_map = {}
all_feats = []
#prop = index.Property()
#prop.overwrite = True
#idx = index.Index('rtree', idx_gen(prepared_map, all_feats))
idx = index.Index(idx_gen(prepared_map, all_feats))


edges = []
with open('data/edges_nodata.geojsonl', 'r') as f:
    for line in f:
        line = line.strip()
        if line == '':
            continue
        feat = json.loads(line)
        edges.append(shape(feat['geometry']))

print('filtering to obtain only shapes at tile edges')
to_consider = {}

for s in edges:
    intersecting_ids = list(idx.intersection(s.bounds, objects='raw'))
    ps = prep(s)

    for idx_fid in intersecting_ids:
        g = prepared_map[idx_fid].context
        if ps.intersects(g):
            to_consider[idx_fid] = g

print(f'{len(to_consider)=}')

def idx_to_consider_gen(to_consider):
    i = 0
    print('generating to_consider_index')
    for fid, s in to_consider.items():
        yield (fid, s.bounds, fid)
        i += 1
        if i % 10000 == 0:
            print(f'done with {i} entries')


to_consider_idx = index.Index(idx_to_consider_gen(to_consider))

print('collecting overlaps')
overlaps = {}
to_merge_geoms = {}
i = 0
for fid, s in to_consider.items():

    if len(s.bounds) == 0:
        continue

    #print(f'handling {fid=}')
    #idx_features = [n.object for n in idx.intersection(s.bounds, objects=True)]
    intersecting_ids = list(to_consider_idx.intersection(s.bounds, objects='raw'))
    #print(f'{intersecting_ids=}')
    for idx_fid in intersecting_ids:
        if idx_fid == fid:
            continue
        pg = prepared_map[idx_fid]
        #print(f'\thandling {idx_fid=}')
        if pg.intersects(s):
            if fid not in overlaps:
                overlaps[fid] = []
            overlaps[fid].append(idx_fid)
            #to_merge_geoms[idx_fid] = pg.context
            to_merge_geoms[idx_fid] = pg.context
            to_merge_geoms[fid] = s
            
    i += 1
    if i % 100 == 0:
        print(f'done with {i} entries')

print(f'dissolving {len(to_merge_geoms)} geoms')

dissolved = unary_union(list(to_merge_geoms.values()))

print('writing to file')
with open('data/merged.geojsonl', 'w') as of:
    print('saving unmerged items')
    with open('data/clipped.geojsonl', 'r') as f:
        for line in f:
            line = line.strip()
            if line == '':
                continue
            feat = json.loads(line)
            fid = feat['properties']['id']
            if fid in to_merge_geoms:
                continue
            of.write(line)
            of.write('\n')

    print('saving merged items')
    count = 0
    i = max_id
    for g in dissolved.geoms:
        i += 1
        count += 1
        feat = {"type": "Feature", "geometry": mapping(g), "properties": {"id": i}}
        of.write(json.dumps(feat))
        of.write('\n')

