import re
import glob

import time
import subprocess

from pathlib import Path

MAX_ZOOM=16

def run_external(cmd):
    print(f'running cmd - {cmd}')
    start = time.time()
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    end = time.time()
    print(f'STDOUT: {res.stdout}')
    print(f'STDERR: {res.stderr}')
    print(f'command took {end - start} secs to run')
    if res.returncode != 0:
        raise Exception(f'command {cmd} failed')


def convert_paths_in_vrt(vrt_file):
    vrt_dirname = str(vrt_file.resolve().parent)
    vrt_text = vrt_file.read_text()
    replaced = re.sub(
        r'<SourceFilename relativeToVRT="1">(.*)</SourceFilename>',
        rf'<SourceFilename relativeToVRT="0">{vrt_dirname}/\1</SourceFilename>',
        vrt_text
    )
    vrt_file.write_text(replaced)


if __name__ == '__main__':
    tiles_dir = Path('export/tiles')

    tiles_dir.mkdir(parents=True, exist_ok=True)
    file_list_file = Path('export/files_to_tile.txt')
    file_names = list(glob.glob('export/gtiffs/*.tif'))
    file_names = [ str(Path(f).resolve()) for f in file_names ]
    print(f' total files: {len(file_names)}')
    file_list_file.write_text('\n'.join(file_names))
    vrt_file = Path('export/files_to_tile.vrt')
    if not vrt_file.exists():
        run_external(f'gdalbuildvrt -input_file_list {str(file_list_file)} {str(vrt_file)}')
        convert_paths_in_vrt(vrt_file)
    run_external(f'gdal2tiles.py -r antialias --verbose --exclude --resume --xyz --processes=8 -z 0-{MAX_ZOOM} --tiledriver WEBP --webp-quality 50 {str(vrt_file)} {str(tiles_dir)}')


