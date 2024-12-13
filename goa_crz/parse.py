import time
import json
import subprocess
from pathlib import Path
from pprint import pprint

import cv2
import numpy as np
from pdfminer.image import ImageWriter
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LTImage
from pdfminer.pdftypes import resolve_all, PDFObjRef, PDFNotImplementedError


inter_dir = Path('inter/')
inter_dir.mkdir(exist_ok=True)

exports_dir = Path('export/gtiffs/')
exports_dir.mkdir(exist_ok=True, parents=True)

def get_images(layout):
    imgs = []
    if isinstance(layout, LTImage):
        imgs.append(layout)

    objs = getattr(layout, '_objs', [])
    for obj in objs:
        imgs.extend(get_images(obj))
    return imgs


def run_external(cmd):
    print(f'running cmd - {cmd}')
    start = time.time()
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    end = time.time()
    print(f'STDOUT: {res.stdout}')
    print(f'STDERR: {res.stderr}')
    print(f'command took {end - start} secs to run')
    if res.returncode != 0:
        raise Exception(f'command {cmd} failed with exit code: {res.returncode}')

def get_file_dir(filename):
    file_p = Path(filename)
    sheet_no = file_p.name.replace('.pdf', '')
    dir_p = Path(inter_dir).joinpath(sheet_no)
    dir_p.mkdir(parents=True, exist_ok=True)
    return dir_p

def crop_img(img, bbox):
    x, y, w, h = bbox
    return img[y:y+h, x:x+w]

index_map = None
def get_full_index():
    global index_map
    if index_map is not None:
        return index_map
    print('loading index file')
    with open('data/goa_grid.geojson', 'r') as f:
        index = json.load(f)
    index_map = {}
    for f in index['features']:
        sheet_no = f['properties']['MAP_NO']
        geom = f['geometry']
        index_map[sheet_no] = geom
    return index_map



class Converter:
    def __init__(self, filename):
        self.filename = filename
        self.file_fp = None
        self.file_dir = get_file_dir(filename)
        self.cur_step = None
        self.full_img = None
        self.map_img = None
        self.src_crs = None
        self.mapbox = None
        self.mapbox_corners = None
        self.jpeg_export_quality = 10
        self.warp_jpeg_export_quality = 75

    def get_pdf_doc(self):
        self.file_fp = open(self.filename, "rb")
        parser = PDFParser(self.file_fp)
        document = PDFDocument(parser)
        return document

    def get_full_img_file(self):
        return Path(self.file_dir).joinpath('full.jpg')

    def get_full_img(self):
        if self.full_img is not None:
            return self.full_img
        
        img_file = self.get_full_img_file()
        print('loading full image')
        start = time.time()
        self.full_img = cv2.imread(str(img_file))
        end = time.time()
        print(f'loading image took {end - start} secs')
        return self.full_img

    def get_corners(self):
        if self.mapbox_corners is not None:
            return self.mapbox_corners, self.mapbox

        file_p = Path(filename)
        sheet_no = file_p.name.replace('.pdf', '')
        corners_file = Path(f'corner_locations/{sheet_no}.txt')

        dist_lines = corners_file.read_text().split('\n')
        dist_vals = tuple([ tuple([int(s) for s in l.split(',') if s != '']) for l in dist_lines if l.strip() != '' ])

        d_lt, d_lb, d_rb, d_rt = dist_vals 
        
        full_img = self.get_full_img()
        h, w = full_img.shape[:2]
        c_lt = d_lt
        c_lb = [ d_lb[0], h - d_lb[1] ]
        c_rb = [ w - d_rb[0], h - d_rb[1] ]
        c_rt = [ w - d_rt[0], d_rt[1] ]
        corners = c_lt, c_lb, c_rb, c_rt

        corners_contour = np.array(corners).reshape((-1,1,2)).astype(np.int32)
        bbox = cv2.boundingRect(corners_contour)

        corners_in_box = [ (c[0] - bbox[0], c[1] - bbox[1]) for c in corners ]
        self.mapbox_corners = corners_in_box
        self.mapbox = bbox
        return corners_in_box, bbox


    def get_index_geom(self):
        sheet_no = Path(self.filename).name.replace('.pdf', '').replace('_', '/')
        full_index = get_full_index()
        geom = full_index[sheet_no]
        return geom

    def create_cutline(self, ibox, file):
        sub_geoms = []
        with open(file, 'w') as f:
            cutline_data = {
                "type": "FeatureCollection",
                "name": "CUTLINE",
                "features": [{
                    "type": "Feature",
                    "properties": {},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [ibox]
                    }
                }]
            }
            json.dump(cutline_data, f, indent=4)


    def georeference_mapbox(self):
        #mapbox_file = self.file_dir.joinpath('mapbox.jpg')
        cropped_file = self.file_dir.joinpath('cropped.jpg')
        georef_file  = self.file_dir.joinpath('georef.tif')
        final_file   = self.file_dir.joinpath('final.tif')
        if georef_file.exists() or final_file.exists():
            print(f'{georef_file} or {final_file} exists.. skipping')
            return
        geom = self.get_index_geom()

        sheet_ibox = geom['coordinates'][0]
        ibox = sheet_ibox

        corners, _ = self.get_corners()

        gcp_str = ''
        i = ibox[0]
        c = corners[2]
        gcp_str += f' -gcp {c[0]} {c[1]} {i[0]} {i[1]}'
        i = ibox[1]
        c = corners[1]
        gcp_str += f' -gcp {c[0]} {c[1]} {i[0]} {i[1]}'
        i = ibox[2]
        c = corners[0]
        gcp_str += f' -gcp {c[0]} {c[1]} {i[0]} {i[1]}'
        i = ibox[3]
        c = corners[3]
        gcp_str += f' -gcp {c[0]} {c[1]} {i[0]} {i[1]}'
        perf_options = '--config GDAL_CACHEMAX 128 --config GDAL_NUM_THREADS ALL_CPUS'
        translate_cmd = f'gdal_translate {perf_options} {gcp_str} -a_srs "EPSG:4326" -of GTiff {str(cropped_file)} {str(georef_file)}' 
        run_external(translate_cmd)


    def warp_mapbox(self):
        cutline_file = self.file_dir.joinpath('cutline.geojson')
        georef_file  = self.file_dir.joinpath('georef.tif')
        final_file   = self.file_dir.joinpath('final.tif')
        if final_file.exists():
            print(f'{final_file} exists.. skipping')
            return

        geom = self.get_index_geom()

        sheet_ibox = geom['coordinates'][0]

        def warp_file(box, cline_file, f_file, jpeg_quality):
            img_quality_config = {
                'COMPRESS': 'JPEG',
                #'PHOTOMETRIC': 'YCBCR',
                'JPEG_QUALITY': f'{jpeg_quality}'
            }

            self.create_cutline(box, cline_file)
            cutline_options = f'-cutline {str(cline_file)} -crop_to_cutline --config GDALWARP_IGNORE_BAD_CUTLINE YES -wo CUTLINE_ALL_TOUCHED=TRUE'

            warp_quality_config = img_quality_config.copy()
            warp_quality_config.update({'TILED': 'YES'})
            warp_quality_options = ' '.join([ f'-co {k}={v}' for k,v in warp_quality_config.items() ])
            reproj_options = f'-tps -tr 1 1 -r bilinear -t_srs "EPSG:3857"' 
            #nodata_options = '-dstnodata 0'
            nodata_options = '-dstalpha'
            perf_options = '-multi -wo NUM_THREADS=ALL_CPUS --config GDAL_CACHEMAX 1024 -wm 1024' 
            warp_cmd = f'gdalwarp -overwrite {perf_options} {nodata_options} {reproj_options} {warp_quality_options} {cutline_options} {str(georef_file)} {str(f_file)}'
            run_external(warp_cmd)
            

        sheet_no = Path(self.filename).name.replace('.pdf', '')
        warp_file(sheet_ibox, cutline_file, final_file, self.warp_jpeg_export_quality)


    def export_internal(self, filename, out_filename, jpeg_export_quality):
        if Path(out_filename).exists():
            print(f'{out_filename} exists.. skipping export')
            return
        creation_opts = f'-co TILED=YES -co COMPRESS=JPEG -co JPEG_QUALITY={jpeg_export_quality} -co PHOTOMETRIC=YCBCR' 
        mask_options = '--config GDAL_TIFF_INTERNAL_MASK YES  -b 1 -b 2 -b 3 -mask 4'
        perf_options = '--config GDAL_CACHEMAX 512'
        cmd = f'gdal_translate {perf_options} {mask_options} {creation_opts} {filename} {out_filename}'
        run_external(cmd)


    def export(self):
        filename = str(self.file_dir.joinpath('final.tif'))
        sheet_no = self.file_dir.name
        out_filename = f'export/gtiffs/{sheet_no}.tif'
        self.export_internal(filename, out_filename, self.jpeg_export_quality)

    def convert(self):
        document = self.get_pdf_doc()
     
        if not document.is_extractable:
            raise PDFTextExtractionNotAllowed(
                    "Text extraction is not allowed"
            )
        img_writer = ImageWriter('.')
        rsrcmgr = PDFResourceManager(caching=True)
        device = PDFPageAggregator(rsrcmgr, laparams=None)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        page_info = {}
        pno = 0
        for page in PDFPage.create_pages(document):
            if pno > 0:
                raise Exception('only one page expected')
            interpreter.process_page(page)
            layout = device.get_result()
            page_info = {}
            page_info['layout'] = layout
            images = get_images(layout)
            if len(images) > 1:
                raise Exception('Only one image expected')
            image = images[0]
            print(image)
            print(image.colorspace)

            # fix to pdfminer bug
            if len(image.colorspace) == 1 and isinstance(image.colorspace[0], PDFObjRef):
                image.colorspace = resolve_all(image.colorspace[0])
                if not isinstance(image.colorspace, list):
                    image.colorspace = [ image.colorspace ]
            fname = img_writer.export_image(image)
            print(f'image extracted to {fname}')
            out_filename = str(self.get_full_img_file())
            print(f'writing {out_filename}')
            shutil.move(fname, out_filename)


    def run(self):
        sheet_no = self.file_dir.name
        export_file = Path(f'export/gtiffs/{sheet_no}.tif')
        if export_file.exists():
            print(f'{export_file} exists.. skipping')
            return

        _, bbox = self.get_corners()
        full_img = self.get_full_img()
        cropped_img = crop_img(full_img, bbox)
        cropped_file = self.file_dir.joinpath('cropped.jpg')
        cv2.imwrite(str(cropped_file), cropped_img)
        self.georeference_mapbox()
        self.warp_mapbox()
        self.export()
 

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        raise Exception('mode is not provided')
    mode = sys.argv[1]
    if mode not in ['full', 'convert']:
        raise Exception('mode should be one of "full", "convert"')
    for p in Path('data/').glob('*.pdf'):
        converter = Converter(str(p))
        if mode == 'full':
            converter.run()
        else:
            converter.convert()
