#!/bin/bash

#mkdir data
# download the grid file
#esri2geojson https://gisportal.ncscm.res.in/server/rest/services/CZMP_STATES/INDIA_CZMPPDF/MapServer/16 data/goa_grid.geojson

# extract the images
python parse.py convert

# locate the corners manually and populate the corner_locations/*.txt files

# georeference/crop and prepare the files
python parse.py full

# tile
python tile.py

# create mbtiles file
python collect.py

# convert to pmtiles
pmtiles convert goa_crz.mbtiles goa_crz.pmtiles

