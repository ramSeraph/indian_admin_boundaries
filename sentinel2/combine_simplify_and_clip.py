import json
from pathlib import Path

from shapely.geometry import shape, mapping
from shapely.prepared import prep

def load_india_shape():
    data = json.loads(Path('data/india-composite.geojson').read_text())
    geom = data['features'][0]['geometry']
    return prep(shape(geom))

if __name__ == '__main__':
    count = 0
    india_shape = load_india_shape()
    with open('data/clipped.geojsonl', 'w') as of:
        for p in Path('data/polygonized/').glob('*.geojsonl'):
            with open(p, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line == '':
                        continue
                    feat = json.loads(line)
                    s = shape(feat['geometry'])
                    if not india_shape.intersects(s):
                        continue

                    s = s.simplify(0.0001, preserve_topology=True)
                    feat['geometry'] = mapping(s)
                    count += 1
                    feat['properties'] = { 'id': count }
                    out_line = json.dumps(feat)
                    of.write(out_line)
                    of.write('\n')
