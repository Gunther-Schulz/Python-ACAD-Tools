from owslib.wmts import WebMapTileService
import os
import math
import time


def filter_row_cols_by_bbox(matrix, bbox):
    a = matrix.scaledenominator * 0.00028
    e = matrix.scaledenominator * -0.00028

    column_orig = math.floor(
        (float(bbox[0]) - matrix.topleftcorner[0]) / (a * matrix.tilewidth))
    row_orig = math.floor(
        (float(bbox[1]) - matrix.topleftcorner[1]) / (e * matrix.tilewidth))

    column_dest = math.floor(
        (float(bbox[2]) - matrix.topleftcorner[0]) / (a * matrix.tilewidth))
    row_dest = math.floor(
        (float(bbox[3]) - matrix.topleftcorner[1]) / (e * matrix.tilewidth))

    if column_orig > column_dest:
        column_orig, column_dest = column_dest, column_orig

    if row_orig > row_dest:
        row_orig, row_dest = row_dest, row_orig

    column_dest += 1
    row_dest += 1

    return column_orig, column_dest, row_orig, row_dest


def tile_already_exists(file_path):
    return os.path.exists(file_path)


def write_image(file_path, img):
    with open(file_path, 'wb') as out:
        out.write(img.read())


def write_world_file(file_path, extension, col, row, matrix):
    if extension == 'png':
        wf_ext = 'pgw'
    elif extension in ['tiff', 'tif']:
        wf_ext = 'tfw'
    elif extension in ['jpg', 'jpeg']:
        wf_ext = 'jgw'
    elif extension == 'gif':
        wf_ext = 'gfw'
    else:
        wf_ext = 'wld'

    pixel_size = 0.00028
    a = matrix.scaledenominator * pixel_size
    e = matrix.scaledenominator * -pixel_size
    left = ((col * matrix.tilewidth + 0.5) * a) + matrix.topleftcorner[0]
    top = ((row * matrix.tileheight + 0.5) * e) + matrix.topleftcorner[1]

    with open(f'{file_path}.{wf_ext}', 'w') as f:
        f.write('%f\n%d\n%d\n%f\n%f\n%f' % (a, 0, 0, e, left, top))


def download_wmts_tiles(wmts_info: dict, geltungsbereich, buffer_distance: float, target_folder: str):
    """Download WMTS tiles for the given area with a buffer and save to the target folder."""
    """Source: https://github.com/GastonZalba/wmts-downloader"""

    capabilities_url = wmts_info['url']
    wmts = WebMapTileService(capabilities_url)
    layer_id = wmts_info['layer']
    zoom = wmts_info['zoom']
    format = 'image/png'
    proj = wmts_info['proj']  # Updated projection
    sleep = wmts_info.get('sleep', 0)
    limit_requests = wmts_info.get('limit', 0)

    # Buffer the geltungsbereich
    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)

    # Get bounding box of the buffered geltungsbereich
    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds
    bbox = (minx, miny, maxx, maxy)

    # Create a subdirectory for the zoom level
    zoom_folder = os.path.join(target_folder, f'zoom_{zoom}')
    if not os.path.exists(zoom_folder):
        os.makedirs(zoom_folder)

    def filter_row_cols_by_bbox(matrix, bbox):
        a = matrix.scaledenominator * 0.00028
        e = matrix.scaledenominator * -0.00028

        column_orig = math.floor(
            (float(bbox[0]) - matrix.topleftcorner[0]) / (a * matrix.tilewidth))
        row_orig = math.floor(
            (float(bbox[1]) - matrix.topleftcorner[1]) / (e * matrix.tilewidth))

        column_dest = math.floor(
            (float(bbox[2]) - matrix.topleftcorner[0]) / (a * matrix.tilewidth))
        row_dest = math.floor(
            (float(bbox[3]) - matrix.topleftcorner[1]) / (e * matrix.tilewidth))

        if column_orig > column_dest:
            column_orig, column_dest = column_dest, column_orig

        if row_orig > row_dest:
            row_orig, row_dest = row_dest, row_orig

        column_dest += 1
        row_dest += 1

        return column_orig, column_dest, row_orig, row_dest

    def tile_already_exists(file_name, extension):
        file_path = os.path.join(zoom_folder, f'{file_name}.{extension}')
        return os.path.exists(file_path)

    def write_image(file_name, extension, img):
        file_path = os.path.join(zoom_folder, f'{file_name}.{extension}')
        with open(file_path, 'wb') as out:
            out.write(img.read())

    def write_world_file(file_name, extension, col, row, matrix):
        if extension == 'png':
            wf_ext = 'pgw'
        elif extension in ['tiff', 'tif']:
            wf_ext = 'tfw'
        elif extension in ['jpg', 'jpeg']:
            wf_ext = 'jgw'
        elif extension == 'gif':
            wf_ext = 'gfw'
        else:
            wf_ext = 'wld'

        pixel_size = 0.00028
        a = matrix.scaledenominator * pixel_size
        e = matrix.scaledenominator * -pixel_size
        left = ((col * matrix.tilewidth + 0.5) * a) + matrix.topleftcorner[0]
        top = ((row * matrix.tileheight + 0.5) * e) + matrix.topleftcorner[1]

        with open(os.path.join(zoom_folder, f'{file_name}.{wf_ext}'), 'w') as f:
            f.write('%f\n%d\n%d\n%f\n%f\n%f' % (a, 0, 0, e, left, top))

    try:
        wmts = WebMapTileService(capabilities_url)

        layer = wmts.contents[layer_id]
        print(f"Available tile matrix sets: {layer.tilematrixsetlinks.keys()}")

        if proj not in layer.tilematrixsetlinks:
            raise ValueError(
                f"Projection {proj} not available for layer {layer_id}")

        tile_matrix_set = layer.tilematrixsetlinks[proj]

        tile_matrix = wmts.tilematrixsets[proj].tilematrix
        print(f"Available zoom levels: {tile_matrix.keys()}")

        if str(zoom) not in tile_matrix:
            raise ValueError(
                f"Zoom level {zoom} not available for projection {proj}")

        tile_matrix_zoom = tile_matrix[str(zoom)]

        # Ensure zoom level is accessed as a string
        zoom_str = str(zoom)
        if zoom_str in tile_matrix_set.tilematrixlimits:
            min_row = tile_matrix_set.tilematrixlimits[zoom_str].mintilerow
            max_row = tile_matrix_set.tilematrixlimits[zoom_str].maxtilerow
            min_col = tile_matrix_set.tilematrixlimits[zoom_str].mintilecol
            max_col = tile_matrix_set.tilematrixlimits[zoom_str].maxtilecol
        else:
            # If tilematrixlimits are not available, use the entire range
            min_row = 0
            max_row = tile_matrix_zoom.matrixheight
            min_col = 0
            max_col = tile_matrix_zoom.matrixwidth

        print(
            f"Tile matrix limits - Min row: {min_row}, Max row: {max_row}, Min col: {min_col}, Max col: {max_col}")

        min_col, max_col, min_row, max_row = filter_row_cols_by_bbox(
            tile_matrix_zoom, bbox)

        download_count = 0
        skip_count = 0

        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                extension = format.split("/")[-1]
                file_name = f'{layer_id}__{proj.replace(":", "-")}_row-{row}_col-{col}_zoom-{zoom}'

                if tile_already_exists(file_name, extension):
                    skip_count += 1
                    continue

                img = wmts.gettile(layer=layer_id, tilematrixset=proj,
                                   tilematrix=zoom_str, row=row, column=col, format=format)

                write_world_file(file_name,
                                 extension, col, row, tile_matrix_zoom)
                write_image(file_name, extension, img)

                download_count += 1
                if limit_requests and download_count >= limit_requests:
                    break

                if sleep:
                    time.sleep(sleep)
            else:
                continue
            break

    except Exception as e:
        print(f'Error: {e}')
