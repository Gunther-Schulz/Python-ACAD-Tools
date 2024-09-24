from owslib.wmts import WebMapTileService
from owslib.wms import WebMapService
import os
import math
import time
import mimetypes
from src.utils import log_info, log_warning, log_error
from PIL import Image, ImageOps
from io import BytesIO
from collections import defaultdict
import logging
import numpy as np

# This will also log INFO
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def color_distance(c1, c2):
    return np.sqrt(np.sum((c1 - c2) ** 2))

def post_process_image(img, color_map, alpha_color, tolerance=30, grayscale=False):
    img = img.convert('RGBA')
    data = np.array(img)
    
    for target_color, replacement_color in color_map.items():
        distances = np.apply_along_axis(lambda x: color_distance(x[:3], np.array(hex_to_rgb(target_color))), 2, data)
        mask = distances <= tolerance
        data[mask] = np.append(hex_to_rgb(replacement_color), 255)
    
    if alpha_color:
        alpha_distances = np.apply_along_axis(lambda x: color_distance(x[:3], np.array(hex_to_rgb(alpha_color))), 2, data)
        alpha_mask = alpha_distances <= tolerance
        data[alpha_mask, 3] = 0
    
    result_img = Image.fromarray(data)
    
    if grayscale:
        # Convert to grayscale while preserving alpha channel
        gray_data = np.array(ImageOps.grayscale(result_img.convert('RGB')))
        alpha_channel = data[:, :, 3]
        gray_rgba = np.dstack((gray_data, gray_data, gray_data, alpha_channel))
        result_img = Image.fromarray(gray_rgba)
    
    return result_img

def hex_to_rgb(hex_color):
    return tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

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


def tile_already_exists(file_name, extension, zoom_folder):
    for ext in ['png', 'jpg']:
        file_path = os.path.join(zoom_folder, f'{file_name}.{ext}')
        if os.path.exists(file_path):
            return True, file_path, ext
    return False, os.path.join(zoom_folder, f'{file_name}.{extension}'), extension


def write_image(file_name, extension, img, zoom_folder):
    file_path = os.path.join(zoom_folder, f'{file_name}.{extension}')
    with open(file_path, 'wb') as out:
        out.write(img.read())
    return file_path


def get_world_file_extension(image_extension: str) -> str:
    extension_map = {
        'png': 'pgw',
        'tiff': 'tfw',
        'tif': 'tfw',
        'jpg': 'jgw',
        'jpeg': 'jgw',
        'gif': 'gfw'
    }
    return extension_map.get(image_extension.lower(), 'wld')


def write_world_file(file_name, extension, col, row, matrix, zoom_folder) -> str:
    wf_ext = get_world_file_extension(extension)
    pixel_size = 0.00028
    a = matrix.scaledenominator * pixel_size
    e = matrix.scaledenominator * -pixel_size
    left = ((col * matrix.tilewidth + 0.5) * a) + matrix.topleftcorner[0]
    top = ((row * matrix.tileheight + 0.5) * e) + matrix.topleftcorner[1]

    world_file_path = os.path.join(zoom_folder, f'{file_name}.{wf_ext}')
    with open(world_file_path, 'w') as f:
        f.write('%f\n%d\n%d\n%f\n%f\n%f' % (a, 0, 0, e, left, top))

    return world_file_path

def download_wmts_tiles(wmts_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, update: bool = False, overwrite: bool = False) -> list:
    capabilities_url = wmts_info['url']
    wmts = WebMapTileService(capabilities_url)
    layer_id = wmts_info['layer']
    zoom = wmts_info['zoom']
    requested_format = wmts_info.get('format', 'image/png')
    requested_extension = requested_format.split("/")[-1]
    proj = wmts_info['proj']
    sleep = wmts_info.get('sleep', 0)
    limit_requests = wmts_info.get('limit', 0)

    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)

    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds
    bbox = (minx, miny, maxx, maxy)

    zoom_folder = target_folder

    downloaded_tiles = []
    download_count = 0
    skip_count = 0

    try:
        wmts = WebMapTileService(capabilities_url)

        layer = wmts.contents[layer_id]
        log_info(f"Available tile matrix sets:")
        for tms in wmts.contents[layer_id].tilematrixsetlinks.keys():
            print(f"  • {tms}")

        if proj not in layer.tilematrixsetlinks:
            raise ValueError(
                f"Projection {proj} not available for layer {layer_id}")

        tile_matrix_set = layer.tilematrixsetlinks[proj]

        tile_matrix = wmts.tilematrixsets[proj].tilematrix
        log_info(f"Available zoom levels: {', '.join(tile_matrix.keys())}")

        if str(zoom) not in tile_matrix:
            raise ValueError(
                f"Zoom level {zoom} not available for projection {proj}")

        tile_matrix_zoom = tile_matrix[str(zoom)]

        zoom_str = str(zoom)
        if zoom_str in tile_matrix_set.tilematrixlimits:
            min_row = tile_matrix_set.tilematrixlimits[zoom_str].mintilerow
            max_row = tile_matrix_set.tilematrixlimits[zoom_str].maxtilerow
            min_col = tile_matrix_set.tilematrixlimits[zoom_str].mintilecol
            max_col = tile_matrix_set.tilematrixlimits[zoom_str].maxtilecol
        else:
            min_row = 0
            max_row = tile_matrix_zoom.matrixheight
            min_col = 0
            max_col = tile_matrix_zoom.matrixwidth

        print(
            f"Tile matrix limits - Min row: {min_row}, Max row: {max_row}, Min col: {min_col}, Max col: {max_col}")

        min_col, max_col, min_row, max_row = filter_row_cols_by_bbox(
            tile_matrix_zoom, bbox)

        log_info(f"Starting download_wmts_tiles with update={update}, overwrite={overwrite}")
        log_info(f"Target folder: {target_folder}")
        log_info(f"Requested format: {wmts_info.get('format', 'image/png')}")

        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                file_name = f'{layer_id}__{proj.replace(":", "-")}_row-{row}_col-{col}_zoom-{zoom}'
                
                exists, file_path, existing_extension = tile_already_exists(file_name, requested_extension, zoom_folder)
                
                if exists and (not update or (update and not overwrite)):
                    world_file_path = f'{zoom_folder}/{file_name}.{get_world_file_extension(existing_extension)}'
                    downloaded_tiles.append((file_path, world_file_path))
                    skip_count += 1
                    continue

                img = wmts.gettile(layer=layer_id, tilematrixset=proj,
                                tilematrix=zoom_str, row=row, column=col, format=requested_format)

                content_type = img.info().get('Content-Type', requested_format)
                actual_extension = mimetypes.guess_extension(content_type, strict=False)
                if actual_extension is None:
                    actual_extension = requested_extension
                else:
                    actual_extension = actual_extension[1:]

                world_file_path = write_world_file(
                    file_name, actual_extension, col, row, tile_matrix_zoom, zoom_folder)
                file_path = write_image(
                    file_name, actual_extension, img, zoom_folder)

                downloaded_tiles.append((file_path, world_file_path))
                download_count += 1

                if limit_requests and download_count >= limit_requests:
                    print(f"Reached download limit of {limit_requests}")
                    break

                if sleep:
                    time.sleep(sleep)
            else:
                continue
            break

    except Exception as e:
        print(f'Error: {e}')

    log_info(f"Total tiles processed: {download_count + skip_count}")
    log_info(f"Tiles downloaded: {download_count}")
    log_info(f"Tiles skipped (already exist): {skip_count}")

    return downloaded_tiles

def download_wms_tiles(wms_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, update: bool = False, overwrite: bool = False) -> list:
    log_info(f"Starting download_wms_tiles with the following parameters:")
    log_info(f"WMS Info: {wms_info}")
    log_info(f"Buffer distance: {buffer_distance}")
    log_info(f"Target folder: {target_folder}")
    log_info(f"Update: {update}, Overwrite: {overwrite}")

    capabilities_url = wms_info['url']
    try:
        wms = WebMapService(capabilities_url, version=wms_info.get('version', '1.3.0'))
    except Exception as e:
        log_error(f"Failed to connect to WMS service: {str(e)}")
        return []

    print("Available layers from WMS endpoint:")
    for layer_name, layer in wms.contents.items():
        print(f"  • {layer_name}: {layer.title}")

    layer_id = wms_info['layer']
    if layer_id not in wms.contents:
        log_error(f"Layer '{layer_id}' not found in WMS service. Please choose from the available layers listed above.")
        return []

    srs = wms_info['srs']
    image_format = wms_info.get('format', 'image/png')
    tile_size = wms_info.get('tileSize', 256)
    sleep = wms_info.get('sleep', 0)
    limit_requests = wms_info.get('limit', 0)
    zoom = wms_info.get('zoom')

    post_process = wms_info.get('postProcess', {})
    color_map = post_process.get('colorMap', {})
    alpha_color = post_process.get('alphaColor')
    tolerance = post_process.get('tolerance', 30)
    grayscale = post_process.get('grayscale', False)  # Add this line

    logging.info(f"Post-processing config: color_map={color_map}, alpha_color={alpha_color}, tolerance={tolerance}, grayscale={grayscale}")

    log_info(f"WMS Info: {wms_info}")

    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)

    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds
    bbox = (minx, miny, maxx, maxy)

    width = maxx - minx
    height = maxy - miny

    if zoom is not None:
        tile_size = tile_size * (2 ** (18 - zoom))

    cols = math.ceil(width / tile_size)
    rows = math.ceil(height / tile_size)

    log_info(f"Downloading {rows}x{cols} tiles")

    downloaded_tiles = []
    download_count = 0
    skip_count = 0  # Add this line

    for row in range(rows):
        for col in range(cols):
            tile_minx = minx + col * tile_size
            tile_miny = miny + row * tile_size
            tile_maxx = min(tile_minx + tile_size, maxx)
            tile_maxy = min(tile_miny + tile_size, maxy)
            tile_bbox = (tile_minx, tile_miny, tile_maxx, tile_maxy)

            file_name = f'{layer_id}__{srs.replace(":", "-")}_row-{row}_col-{col}'
            image_path = os.path.join(target_folder, f'{file_name}.png')
            world_file_path = os.path.join(target_folder, f'{file_name}.pgw')

            if os.path.exists(image_path) and os.path.exists(world_file_path) and (not update or (update and not overwrite)):
                downloaded_tiles.append((image_path, world_file_path))
                skip_count += 1  # Add this line
                continue

            try:
                img = wms.getmap(layers=[layer_id], srs=srs, bbox=tile_bbox, size=(tile_size, tile_size), format=image_format)
                
                if color_map or alpha_color or grayscale:
                    pil_img = Image.open(BytesIO(img.read()))
                    pil_img = post_process_image(pil_img, color_map, alpha_color, tolerance, grayscale)
                    pil_img.save(image_path, 'PNG')
                else:
                    with open(image_path, 'wb') as out:
                        out.write(img.read())

                with open(world_file_path, 'w') as wf:
                    wf.write(f"{(tile_maxx - tile_minx) / tile_size}\n")
                    wf.write("0\n0\n")
                    wf.write(f"-{(tile_maxy - tile_miny) / tile_size}\n")
                    wf.write(f"{tile_minx}\n")
                    wf.write(f"{tile_maxy}\n")

                downloaded_tiles.append((image_path, world_file_path))
                download_count += 1
                log_info(f"Downloaded and processed tile {download_count}: {file_name}")

            except Exception as e:
                logging.error(f"Failed to download or process tile {file_name}: {str(e)}", exc_info=True)

            if limit_requests and download_count >= limit_requests:
                log_info(f"Reached download limit of {limit_requests}")
                return downloaded_tiles

            if sleep:
                time.sleep(sleep)

    log_info(f"Total WMS tiles processed: {download_count + skip_count}")  # Modify this line
    log_info(f"WMS tiles downloaded: {download_count}")
    log_info(f"WMS tiles skipped (already exist): {skip_count}")  # Add this line
    return downloaded_tiles