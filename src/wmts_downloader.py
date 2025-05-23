from owslib.wmts import WebMapTileService
from owslib.wms import WebMapService
import os
import math
import time
import mimetypes
from src.utils import log_info, log_warning, log_error, log_debug
from PIL import Image, ImageOps
from io import BytesIO
from collections import defaultdict
import numpy as np
import cv2
import easyocr
import traceback
# import logging
import src.easyocr_patch

# This will also log INFO
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def color_distance(c1, c2):
    return np.sqrt(np.sum((c1 - c2) ** 2))


def remove_geobasis_text(img):
    log_debug("Attempting to remove GeoBasis-DE/MV text using EasyOCR")

    # Convert PIL Image to OpenCV format
    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # Initialize EasyOCR
    reader = easyocr.Reader(['de', 'en'])

    # Focus on the top portion of the image, but use full width
    height, width = cv_img.shape[:2]
    roi = cv_img[0:int(height*0.09), 0:width]

    # Perform text detection with lower confidence threshold
    results = reader.readtext(roi, min_size=3, low_text=0.1,
                              text_threshold=0.3, link_threshold=0.1, width_ths=0.05)

    texts_to_remove = []
    for (bbox, text, prob) in results:
        log_debug(f"EasyOCR detected text: {text} (confidence: {prob})")
        texts_to_remove.append(text)
        (top_left, top_right, bottom_right, bottom_left) = bbox
        x = int(min(top_left[0], bottom_left[0]))
        y = int(min(top_left[1], top_right[1]))
        w = int(max(top_right[0], bottom_right[0]) - x)
        h = int(max(bottom_left[1], bottom_right[1]) - y)
        # Instead of inpainting, fill the area with white
        cv2.rectangle(roi, (x, y), (x+w, y+h), (255, 255, 255), -1)

    # Print the texts that will be removed
    if texts_to_remove:
        log_debug(f"The following text will be removed: {
                  ', '.join(texts_to_remove)}")
    else:
        log_debug("No text detected for removal")

    # Convert back to PIL Image
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


def post_process_image(img, color_map, alpha_color, tolerance=30, grayscale=False, remove_text=False, retain_if_color_present=None):
    # Convert to numpy array once at the start
    data = np.array(img.convert('RGB'))

    # If we need to check for specific colors, do it first to potentially skip processing
    if retain_if_color_present and 'colors' in retain_if_color_present:
        filter_tolerance = retain_if_color_present.get('tolerance', 5)
        # Convert target colors to numpy arrays once
        target_colors = [np.array(hex_to_rgb(color))
                         for color in retain_if_color_present['colors']]

        # Vectorized color check
        found_any_color = False
        for target_rgb in target_colors:
            # Broadcast subtraction and compute distances in one operation
            distances = np.sqrt(np.sum((data - target_rgb) ** 2, axis=2))
            if np.any(distances <= filter_tolerance):
                found_any_color = True
                break

        if not found_any_color:
            return Image.new('RGBA', img.size, (0, 0, 0, 0))

    # Apply color mapping if needed
    if color_map:
        for target_color, replacement_color in color_map.items():
            target_rgb = np.array(hex_to_rgb(target_color))
            replacement_rgb = np.array(hex_to_rgb(replacement_color))
            # Vectorized color replacement
            distances = np.sqrt(np.sum((data - target_rgb) ** 2, axis=2))
            mask = distances <= tolerance
            data[mask] = replacement_rgb

    # Convert to grayscale if needed
    if grayscale:
        # Use mean across RGB channels for grayscale conversion
        gray_data = np.mean(data, axis=2).astype(np.uint8)
        data = np.stack((gray_data,) * 3, axis=-1)

    # Add alpha channel if needed
    if alpha_color:
        alpha_rgb = np.array(hex_to_rgb(alpha_color))
        # Compute alpha mask in one operation
        distances = np.sqrt(np.sum((data - alpha_rgb) ** 2, axis=2))
        alpha_channel = np.where(
            distances <= tolerance, 0, 255).astype(np.uint8)
        data = np.dstack((data, alpha_channel))

    # Convert back to PIL Image
    mode = 'RGBA' if alpha_color else 'RGB'
    return Image.fromarray(data, mode)


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


def download_wmts_tiles(wmts_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, overwrite: bool = False) -> list:
    log_info(f"Starting WMTS download to target folder: {target_folder}")
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
        log_debug(f"Available tile matrix sets:")
        for tms in wmts.contents[layer_id].tilematrixsetlinks.keys():
            log_info(f"  • {tms}")

        if proj not in layer.tilematrixsetlinks:
            raise ValueError(
                f"Projection {proj} not available for layer {layer_id}")

        tile_matrix_set = layer.tilematrixsetlinks[proj]

        tile_matrix = wmts.tilematrixsets[proj].tilematrix
        log_debug(f"Available zoom levels: {', '.join(tile_matrix.keys())}")

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

        log_info(
            f"Tile matrix limits - Min row: {min_row}, Max row: {max_row}, Min col: {min_col}, Max col: {max_col}")

        min_col, max_col, min_row, max_row = filter_row_cols_by_bbox(
            tile_matrix_zoom, bbox)

        log_debug(f"Starting download_wmts_tiles with overwrite={overwrite}")
        log_debug(f"Target folder: {target_folder}")
        log_debug(f"Requested format: {wmts_info.get('format', 'image/png')}")

        for row in range(min_row, max_row):
            for col in range(min_col, max_col):
                file_name = f'{layer_id}__{proj.replace(
                    ":", "-")}_row-{row}_col-{col}_zoom-{zoom}'

                exists, file_path, existing_extension = tile_already_exists(
                    file_name, requested_extension, zoom_folder)

                if exists and not overwrite:
                    world_file_path = f'{
                        zoom_folder}/{file_name}.{get_world_file_extension(existing_extension)}'
                    downloaded_tiles.append((file_path, world_file_path))
                    skip_count += 1
                    continue

                img = wmts.gettile(layer=layer_id, tilematrixset=proj,
                                   tilematrix=zoom_str, row=row, column=col, format=requested_format)

                content_type = img.info().get('Content-Type', requested_format)
                actual_extension = mimetypes.guess_extension(
                    content_type, strict=False)
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
                    log_info(f"Reached download limit of {limit_requests}")
                    break

                if sleep:
                    time.sleep(sleep)
            else:
                continue
            break

    except Exception as e:
        log_info(f'Error: {e}')

    log_debug(f"Total tiles processed: {download_count + skip_count}")
    log_debug(f"Tiles downloaded: {download_count}")
    log_debug(f"Tiles skipped (already exist): {skip_count}")

    return downloaded_tiles


def download_wms_tiles(wms_info: dict, geltungsbereich, buffer_distance: float, target_folder: str, overwrite: bool = False) -> list:
    log_info(f"Starting WMS download to target folder: {target_folder}")
    log_debug(f"WMS URL: {wms_info['url']}")
    log_debug(f"Layer: {wms_info['layer']}")
    log_debug(f"Target folder: {target_folder}")
    log_debug(f"Overwrite: {overwrite}")

    capabilities_url = wms_info['url']
    try:
        wms = WebMapService(
            capabilities_url, version=wms_info.get('version', '1.3.0'))
    except Exception as e:
        log_error(f"Failed to connect to WMS service: {str(e)}")
        return []

    log_info("Available layers from WMS endpoint:")
    for layer_name, layer in wms.contents.items():
        log_info(f"  • {layer_name}: {layer.title}")

    layer_id = wms_info['layer']
    if layer_id not in wms.contents:
        log_error(f"Layer '{
                  layer_id}' not found in WMS service. Please choose from the available layers listed above.")
        return []

    srs = wms_info['srs']
    image_format = wms_info.get('format', 'image/png')
    tile_width = wms_info.get('width', 256)
    tile_height = wms_info.get('height', 256)
    sleep = wms_info.get('sleep', 0)
    limit_requests = wms_info.get('limit', 0)
    # Remove zoom reference here

    post_process = wms_info.get('postProcess', {})
    color_map = post_process.get('colorMap', {})
    alpha_color = post_process.get('alphaColor')
    tolerance = post_process.get('tolerance', 30)
    grayscale = post_process.get('grayscale', False)
    remove_text = post_process.get('removeText', False)
    retain_if_color_present = post_process.get(
        'retainIfColorPresent')  # Updated name

    log_debug(f"Post-processing config: color_map={color_map}, alpha_color={alpha_color}, tolerance={
              tolerance}, grayscale={grayscale}, remove_text={remove_text}, retain_if_color_present={retain_if_color_present}")

    geltungsbereich_buffered = geltungsbereich.buffer(buffer_distance)
    minx, miny, maxx, maxy = geltungsbereich_buffered.bounds

    # Calculate the number of tiles needed to cover the area
    cols = math.ceil((maxx - minx) / tile_width)
    rows = math.ceil((maxy - miny) / tile_height)

    log_debug(f"Downloading {rows}x{cols} tiles with size {
              tile_width}x{tile_height}")

    downloaded_tiles = []
    download_count = 0
    skip_count = 0

    for row in range(rows):
        for col in range(cols):
            tile_minx = minx + col * tile_width
            # Start from top-left corner
            tile_miny = maxy - (row + 1) * tile_height
            tile_maxx = tile_minx + tile_width
            tile_maxy = tile_miny + tile_height
            tile_bbox = (tile_minx, tile_miny, tile_maxx, tile_maxy)

            file_name = f'{layer_id}__{
                srs.replace(":", "-")}_row-{row}_col-{col}'
            image_path = os.path.join(target_folder, f'{file_name}.png')
            world_file_path = os.path.join(target_folder, f'{file_name}.pgw')

            if os.path.exists(image_path) and os.path.exists(world_file_path) and not overwrite:
                downloaded_tiles.append((image_path, world_file_path))
                skip_count += 1
                continue

            try:
                params = {
                    'layers': [layer_id],
                    'srs': srs,
                    'bbox': tile_bbox,
                    'size': (tile_width, tile_height),
                    'format': image_format,
                }

                img = wms.getmap(**params)

                if color_map or alpha_color or grayscale or remove_text or retain_if_color_present:
                    pil_img = Image.open(BytesIO(img.read()))
                    pil_img = post_process_image(
                        pil_img, color_map, alpha_color, tolerance, grayscale, remove_text, retain_if_color_present)
                    pil_img.save(image_path, 'PNG')
                else:
                    with open(image_path, 'wb') as out:
                        out.write(img.read())

                # Write the world file with correct georeference information
                with open(world_file_path, 'w') as wf:
                    # pixel size in the x-direction
                    wf.write(f"{tile_width / tile_width}\n")
                    wf.write("0\n0\n")  # rotation terms (usually 0)
                    # negative pixel size in the y-direction
                    wf.write(f"-{tile_height / tile_height}\n")
                    # x-coordinate of the center of the upper-left pixel
                    wf.write(f"{tile_minx}\n")
                    # y-coordinate of the center of the upper-left pixel
                    wf.write(f"{tile_maxy}\n")

                downloaded_tiles.append((image_path, world_file_path))
                download_count += 1
                log_debug(f"Downloaded and processed tile {
                          download_count}: {file_name}")

            except Exception as e:
                log_error(f"Failed to download or process tile {
                          file_name}: {str(e)}")
                log_error(f"Traceback: {traceback.format_exc()}")

            if limit_requests and download_count >= limit_requests:
                log_debug(f"Reached download limit of {limit_requests}")
                return downloaded_tiles

            if sleep:
                time.sleep(sleep)

    log_debug(f"Total WMS tiles processed: {download_count + skip_count}")
    log_debug(f"WMS tiles downloaded: {download_count}")
    log_debug(f"WMS tiles skipped (already exist): {skip_count}")
    return downloaded_tiles


def stitch_tiles(tiles, tile_matrix):
    if not tiles:
        raise ValueError("No tiles to stitch")

    # Extract row and column information from filenames
    tile_info = []
    for tile_path, _ in tiles:
        filename = os.path.basename(tile_path)
        parts = filename.split('_')
        row = col = None
        for part in parts:
            if part.startswith('row-'):
                row = int(part.split('-')[1])
            elif part.startswith('col-'):
                # Remove file extension
                col = int(part.split('-')[1].split('.')[0])

        # If row and col are not found, try to extract from WMS filename format
        if row is None or col is None:
            parts = filename.replace('.png', '').split('_')
            if len(parts) >= 2:
                row = int(parts[-2])
                col = int(parts[-1])

        if row is not None and col is not None:
            tile_info.append((row, col, tile_path))
        else:
            log_warning(
                f"Could not extract row and column from filename: {filename}")

    if not tile_info:
        raise ValueError(
            "Could not extract row and column information from tile filenames")

    min_row = min(info[0] for info in tile_info)
    max_row = max(info[0] for info in tile_info)
    min_col = min(info[1] for info in tile_info)
    max_col = max(info[1] for info in tile_info)

    # Open the first image to get tile dimensions
    first_img = Image.open(tile_info[0][2])
    tile_width, tile_height = first_img.size

    width = (max_col - min_col + 1) * tile_width
    height = (max_row - min_row + 1) * tile_height

    stitched_image = Image.new('RGBA', (width, height))

    for row, col, tile_path in tile_info:
        img = Image.open(tile_path)
        stitched_image.paste(
            img, ((col - min_col) * tile_width, (row - min_row) * tile_height))

    # Calculate world file content
    if tile_matrix:
        pixel_size_x = tile_matrix.scaledenominator * 0.00028
        pixel_size_y = -pixel_size_x
        left = tile_matrix.topleftcorner[0] + \
            min_col * tile_width * pixel_size_x
        top = tile_matrix.topleftcorner[1] + \
            min_row * tile_height * pixel_size_y
    else:
        # For WMS, we need to calculate these values from the world files
        world_file_path = tiles[0][1]
        with open(world_file_path, 'r') as wf:
            world_file_content = wf.readlines()
        pixel_size_x = float(world_file_content[0])
        pixel_size_y = float(world_file_content[3])
        left = float(world_file_content[4]) + \
            min_col * tile_width * pixel_size_x
        top = float(world_file_content[5]) + \
            min_row * tile_height * pixel_size_y

    world_file_content = f"{pixel_size_x}\n0\n0\n{pixel_size_y}\n{left}\n{top}"

    return stitched_image, world_file_content


def process_and_stitch_tiles(wmts_info: dict, downloaded_tiles: list, tile_matrix_zoom, zoom_folder: str, layer_name: str) -> list:
    log_debug(f"Stitching tiles for layer: {layer_name}")

    if not downloaded_tiles:
        log_debug(f"No tiles to stitch for layer {layer_name}")
        return []

    stitched_image, world_file_content = stitch_tiles(
        downloaded_tiles, tile_matrix_zoom)

    base_filename = f"{layer_name}_stitched"
    stitched_image_path = os.path.join(zoom_folder, f"{base_filename}.png")
    world_file_path = os.path.join(zoom_folder, f"{base_filename}.pgw")

    files_exist = os.path.exists(
        stitched_image_path) or os.path.exists(world_file_path)
    should_overwrite = wmts_info.get('overwrite', False)

    if files_exist and not should_overwrite:
        log_debug(f"Stitched image already exists and overwrite is not enabled: {
                  stitched_image_path}")
        return [(stitched_image_path, world_file_path)]

    stitched_image.save(stitched_image_path)
    log_debug(f"Saved stitched image: {stitched_image_path}")
    with open(world_file_path, 'w') as f:
        f.write(world_file_content)
    log_debug(f"Saved world file: {world_file_path}")

    return [(stitched_image_path, world_file_path)]


def group_connected_tiles(tiles):
    tile_dict = {}
    for tile_path, world_file_path in tiles:
        filename = os.path.basename(tile_path)
        parts = filename.split('_')
        row = col = None
        for part in parts:
            if part.startswith('row-'):
                row = int(part.split('-')[1])
            elif part.startswith('col-'):
                col = int(part.split('-')[1])
        if row is not None and col is not None:
            tile_dict[(row, col)] = (tile_path, world_file_path)

    def get_neighbors(row, col):
        return [(row-1, col), (row+1, col), (row, col-1), (row, col+1)]

    def dfs(row, col, group):
        if (row, col) not in tile_dict or (row, col) in visited:
            return
        visited.add((row, col))
        group.append(tile_dict[(row, col)])
        for nr, nc in get_neighbors(row, col):
            dfs(nr, nc, group)

    visited = set()
    groups = []
    for (row, col) in tile_dict:
        if (row, col) not in visited:
            group = []
            dfs(row, col, group)
            groups.append(group)

    return groups
