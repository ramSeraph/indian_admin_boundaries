import json
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.prepared import prep

if __name__ == '__main__':
    count = 0
    with open('data/edges_nodata.geojsonl', 'w') as of:
        for p in Path('data/polygonized_nodata/').glob('*.geojsonl'):
            with open(p, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line == '':
                        continue
                    feat = json.loads(line)
                    s = shape(feat['geometry'])
                    s = s.buffer(0.0001, cap_style='square')
                    s = s.simplify(0.0001, preserve_topology=True)
                    feat['geometry'] = mapping(s)
                    count += 1
                    feat['properties'] = { 'id': count }
                    out_line = json.dumps(feat)
                    of.write(out_line)
                    of.write('\n')
