from owslib.wmts import WebMapTileService
from owslib.wms import WebMapService
import os
import math
import time
import mimetypes
from src.utils import log_info, log_warning, log_error
from PIL import Image
from io import BytesIO


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
            log_info(f"Checking if tile exists: {file_path}, Exists: True")
            return True, file_path, ext
    # log_info(f"Checking if tile exists: {os.path.join(zoom_folder, f'{file_name}.png')}, Exists: False")
    return False, os.path.join(zoom_folder, f'{file_name}.{extension}'), extension


def write_image(file_name, extension, img, zoom_folder):
    file_path = os.path.join(zoom_folder, f'{file_name}.{extension}')
    with open(file_path, 'wb') as out:
        out.write(img.read())
    # log_info(f"Image written to: {file_path}")
    # log_info(f"File exists after writing: {os.path.exists(file_path)}")
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

    # Generate the world file path without the image extension
    world_file_path = os.path.join(zoom_folder, f'{file_name}.{wf_ext}')
    with open(world_file_path, 'w') as f:
        f.write('%f\n%d\n%d\n%f\n%f\n%f' % (a, 0, 0, e, left, top))

    return world_file_path

def download_wmts_tiles(wmts_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, overwrite: bool = False) -> list:
    """Download WMTS tiles for the given area with a buffer and save to the target folder."""
    """Source: https://github.com/GastonZalba/wmts-downloader"""

    capabilities_url = wmts_info['url']
    wmts = WebMapTileService(capabilities_url)
    layer_id = wmts_info['layer']
    zoom = wmts_info['zoom']
    requested_format = wmts_info.get('format', 'image/png')
    requested_extension = requested_format.split("/")[-1]
    proj = wmts_info['proj']  # Updated projection
    sleep = wmts_info.get('sleep', 0)
    limit_requests = wmts_info.get('limit', 0)

    # Buffer the geltungsbereich
    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)

    # Get bounding box of the buffered geltungsbereich
    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds
    bbox = (minx, miny, maxx, maxy)

    # Create a subdirectory for the zoom level
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

        log_info(f"Starting download_wmts_tiles with overwrite={overwrite}")
        log_info(f"Target folder: {target_folder}")
        log_info(f"Requested format: {wmts_info.get('format', 'image/png')}")

        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                file_name = f'{layer_id}__{proj.replace(":", "-")}_row-{row}_col-{col}_zoom-{zoom}'
                
                # log_info(f"Processing tile: {file_name}")
                # log_info(f"Requested extension: {requested_extension}")
                
                exists, file_path, existing_extension = tile_already_exists(file_name, requested_extension, zoom_folder)
                # log_info(f"Tile exists: {exists}, Path: {file_path}, Existing extension: {existing_extension}")
                
                if exists and not overwrite:
                    # log_info(f"Skipping existing tile: {file_path}")
                    world_file_path = f'{zoom_folder}/{file_name}.{get_world_file_extension(existing_extension)}'
                    downloaded_tiles.append((file_path, world_file_path))
                    skip_count += 1
                    continue

                # If we get here, we're downloading the tile
                # log_info(f"Downloading tile: {file_name}")

                img = wmts.gettile(layer=layer_id, tilematrixset=proj,
                                tilematrix=zoom_str, row=row, column=col, format=requested_format)

                # Determine the actual extension of the image
                content_type = img.info().get('Content-Type', requested_format)
                actual_extension = mimetypes.guess_extension(content_type, strict=False)
                if actual_extension is None:
                    actual_extension = requested_extension
                else:
                    actual_extension = actual_extension[1:]  # Remove the leading dot

                world_file_path = write_world_file(
                    file_name, actual_extension, col, row, tile_matrix_zoom, zoom_folder)
                file_path = write_image(
                    file_name, actual_extension, img, zoom_folder)

                downloaded_tiles.append((file_path, world_file_path))
                download_count += 1

                # log_info(f"Actual extension determined: {actual_extension}")
                # log_info(f"File path after writing: {file_path}")


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

def download_wms_tiles(wms_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, overwrite: bool = False) -> list:
    """Download WMS tiles for the given area with a buffer and save to the target folder."""
    capabilities_url = wms_info['url']
    try:
        wms = WebMapService(capabilities_url, version=wms_info.get('version', '1.3.0'))
    except Exception as e:
        log_error(f"Failed to connect to WMS service: {str(e)}")
        return []

    # List all available layers
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
    zoom = wms_info.get('zoom')  # New: Get zoom from wms_info

    log_info(f"WMS Info: {wms_info}")

    # Buffer the geltungsbereich
    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)

    # Get bounding box of the buffered geltungsbereich
    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds
    bbox = (minx, miny, maxx, maxy)

    # Calculate the number of tiles needed
    width = maxx - minx
    height = maxy - miny

    # If zoom is provided, adjust tile_size
    if zoom is not None:
        tile_size = tile_size * (2 ** (18 - zoom))  # Adjust this formula based on your WMS provider's zoom levels

    cols = math.ceil(width / tile_size)
    rows = math.ceil(height / tile_size)

    log_info(f"Downloading {rows}x{cols} tiles")

    downloaded_tiles = []
    download_count = 0

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

            if os.path.exists(image_path) and os.path.exists(world_file_path) and not overwrite:
                downloaded_tiles.append((image_path, world_file_path))
                continue

            try:
                img = wms.getmap(layers=[layer_id], srs=srs, bbox=tile_bbox, size=(tile_size, tile_size), format=image_format)
                
                # Save image
                with open(image_path, 'wb') as out:
                    out.write(img.read())

                # Create world file
                with open(world_file_path, 'w') as wf:
                    wf.write(f"{(tile_maxx - tile_minx) / tile_size}\n")
                    wf.write("0\n0\n")
                    wf.write(f"-{(tile_maxy - tile_miny) / tile_size}\n")
                    wf.write(f"{tile_minx}\n")
                    wf.write(f"{tile_maxy}\n")

                downloaded_tiles.append((image_path, world_file_path))
                download_count += 1
                log_info(f"Downloaded tile {download_count}: {file_name}")

            except Exception as e:
                log_error(f"Failed to download tile {file_name}: {str(e)}")

            if limit_requests and download_count >= limit_requests:
                log_info(f"Reached download limit of {limit_requests}")
                return downloaded_tiles

            if sleep:
                time.sleep(sleep)

    log_info(f"Total WMS tiles downloaded: {download_count}")
    return downloaded_tiles