import json
import shutil
import sqlite3
import requests
import mercantile

from pathlib import Path
from pprint import pprint


MAX_ZOOM = 16
out_mbtiles_file = 'goa_crz.mbtiles'

def finalize_mbtiles(conn, cursor):
    cursor.execute(
        "CREATE UNIQUE INDEX tile_index on tiles (zoom_level, tile_column, tile_row);"
    )
    conn.commit()
    cursor.execute("""ANALYZE;""")

    conn.close()


def add_to_mbtiles(p, cursor):
    print(f'adding {p} to mbtiles')
    y = int(p.name.replace('.webp', ''))
    x = int(p.parent.name)
    z = int(p.parent.parent.name)
    flipped_y = (1 << z) - 1 - y
    tile_data = p.read_bytes()
    cursor.execute(
        "INSERT INTO tiles VALUES(?,?,?,?)",
        (z, x, flipped_y, tile_data),
    )


def optimize_cursor(cursor):
    cursor.execute("""PRAGMA synchronous=0""")
    cursor.execute("""PRAGMA locking_mode=EXCLUSIVE""")
    cursor.execute("""PRAGMA journal_mode=DELETE""")


def initialize_tables(cursor, metadata):
    cursor.execute("CREATE TABLE metadata (name text, value text);")
    cursor.execute(
        "CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);"
    )
    for k,v in metadata.items():
        cursor.execute("INSERT INTO metadata VALUES(?,?)", (k, v))

def get_bounds(tileset):
    min_lat = None
    max_lat = None
    min_lon = None
    max_lon = None
    for tile in tileset:
        b = mercantile.bounds(tile)
        if min_lat is None or min_lat > b.south:
            min_lat = b.south
        if max_lat is None or max_lat < b.north:
            max_lat = b.north
        if min_lon is None or min_lon > b.west:
            min_lon = b.west
        if max_lon is None or max_lon < b.east:
            max_lon = b.east
    return min_lat, max_lat, min_lon, max_lon


def get_metadata(tileset):
    m = {}
    min_lat, max_lat, min_lon, max_lon = get_bounds(tileset)
    m["format"] = "webp"
    m["version"] = "2"
    m["type"] = "baselayer"
    m['maxzoom'] = 0
    m['minzoom'] = MAX_ZOOM
    center_lat = (max_lat + min_lat) / 2
    center_lon = (max_lon + min_lon) / 2 
    center_zoom = 0
    m['center'] = f"{center_lon},{center_lat},{center_zoom}"
    m['bounds'] = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    m['attribution'] = 'Source: <a href="https://czmp.ncscm.res.in/">National Centre for Sustainable Coastal Management</a>'
    return m

def get_mbtiles_conn():
    conn = sqlite3.connect(out_mbtiles_file)
    cursor = conn.cursor()
    optimize_cursor(cursor)
    return conn, cursor

if __name__ == '__main__':
    tileset = set()
    for p in Path('export/tiles/').glob('*/*/*.webp'):
        y = int(p.name.replace('.webp', ''))
        x = int(p.parent.name)
        z = int(p.parent.parent.name)
        if z == MAX_ZOOM:
            tile = mercantile.Tile(x=x,y=y,z=z)
            tileset.add(tile)
    metadata = get_metadata(tileset)
    conn, cursor = get_mbtiles_conn()
    initialize_tables(cursor, metadata)
    for p in Path('export/tiles/').glob('*/*/*.webp'):
        add_to_mbtiles(p, cursor)
    finalize_mbtiles(conn, cursor)
