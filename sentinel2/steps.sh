#!/bin/bash

set -ex
mkdir -p data/raw

cat links.txt| xargs -I {} wget -N -P data/raw/ {}
wget -P data/ https://raw.githubusercontent.com/datameet/maps/master/Country/india-composite.geojson

mkdir -p data/webmercator
mkdir -p data/polygonized
mkdir -p data/filtered
mkdir -p data/filtered_nodata
mkdir -p data/polygonized_nodata

export GDAL_PAM_ENABLED=NO
cd data/raw
ls *.tif | xargs -I {} gdal_calc.py --creation-option COMPRESS=LZW --creation-option PREDICTOR=2 --creation-option INTERLEAVE=BAND --creation-option SPARSE_OK=TRUE -A ../raw/{} --outfile=../filtered/{} --calc='A*(A==7)' --NoDataValue=0 --type=Byte
ls *.tif | xargs -I {} gdal_polygonize.py -f GeoJSONSeq ../filtered/{} ../polygonized/{}.geojsonl

ls *.tif | xargs -I {} gdal_calc.py --creation-option COMPRESS=LZW --creation-option PREDICTOR=2 --creation-option INTERLEAVE=BAND --creation-option SPARSE_OK=TRUE -A ../raw/{} --outfile=../filtered_nodata/{} --calc='1*(A==0)' --NoDataValue=0 --type=Byte --hideNoData
ls *.tif | xargs -I {} gdal_polygonize.py -f GeoJSONSeq ../filtered_nodata/{} ../polygonized_nodata/{}.geojsonl
cd -

python combine_simplify_and_clip.py
python get_edges_nodata.py
python merge.py
