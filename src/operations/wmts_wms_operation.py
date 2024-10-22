import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
import os
from src.wmts_downloader import download_wmts_tiles, download_wms_tiles, process_and_stitch_tiles
from owslib.wmts import WebMapTileService
from src.project_loader import ProjectLoader
from src.operations.common_operations import *

def process_wmts_or_wms_layer(all_layers, project_settings, crs, layer_name, operation, project_loader):
    log_info(f"Processing WMTS/WMS layer: {layer_name}")
    log_info(f"Operation details: {operation}")
    
    target_folder = project_loader.resolve_full_path(operation['targetFolder'])
    zoom_level = operation.get('zoom')
    
    zoom_folder = os.path.join(target_folder, f"zoom_{zoom_level}") if zoom_level else target_folder
    
    layer_info = next((l for l in project_settings['geomLayers'] if l['name'] == layer_name), None)
    update_flag = layer_info.get('update', False) if layer_info else False
    overwrite_flag = operation.get('overwrite', False)
    
    os.makedirs(zoom_folder, exist_ok=True)
    
    log_info(f"Target folder path: {zoom_folder}")
    log_info(f"Update flag: {update_flag}, Overwrite flag: {overwrite_flag}")

    layers = operation.get('layers', [])
    buffer_distance = operation.get('buffer', 100)
    service_info = {
        'url': operation['url'],
        'layer': operation['layer'],
        'proj': operation.get('proj'),
        'srs': operation.get('srs'),
        'format': operation.get('format', 'image/png'),
        'sleep': operation.get('sleep', 0),
        'limit': operation.get('limit', 0),
        'postProcess': operation.get('postProcess', {}),
        'overwrite': overwrite_flag,
        'zoom': zoom_level
    }

    service_info['postProcess']['removeText'] = operation.get('postProcess', {}).get('removeText', False)
    service_info['postProcess']['textRemovalMethod'] = operation.get('postProcess', {}).get('textRemovalMethod', 'tesseract')

    stitch_tiles = operation.get('stitchTiles', False)
    service_info['stitchTiles'] = stitch_tiles

    log_info(f"Service info: {service_info}")
    log_info(f"Layers to process: {layers}")

    wmts = WebMapTileService(service_info['url'])
    tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
    available_zooms = sorted(tile_matrix.keys(), key=int)
    
    requested_zoom = service_info.get('zoom')
    
    if requested_zoom is None:
        # Use the highest available zoom level if not specified
        chosen_zoom = available_zooms[-1]
        log_info(f"No zoom level specified. Using highest available zoom: {chosen_zoom}")
    else:
        # Try to use the manually specified zoom level
        if str(requested_zoom) in available_zooms:
            chosen_zoom = str(requested_zoom)
        else:
            error_message = (
                f"Error: Zoom level {requested_zoom} not available for projection {service_info['proj']}.\n"
                f"Available zoom levels: {', '.join(available_zooms)}.\n"
                f"Please choose a zoom level from the available options or remove the 'zoom' key to use the highest available zoom."
            )
            raise ValueError(error_message)
    
    service_info['zoom'] = chosen_zoom
    log_info(f"Using zoom level: {chosen_zoom}")
    
    all_tiles = []
    for layer in layers:
        if layer in all_layers:
            layer_geometry = all_layers[layer]
            if isinstance(layer_geometry, gpd.GeoDataFrame):
                layer_geometry = layer_geometry.geometry.unary_union

            log_info(f"Downloading tiles for layer: {layer}")
            log_info(f"Layer geometry type: {type(layer_geometry)}")
            log_info(f"Layer geometry bounds: {layer_geometry.bounds}")

            if 'wmts' in operation['type'].lower():
                downloaded_tiles = download_wmts_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                wmts = WebMapTileService(service_info['url'])
                tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
                try:
                    tile_matrix_zoom = tile_matrix[str(service_info['zoom'])]
                except KeyError:
                    available_zooms = sorted(tile_matrix.keys())
                    error_message = (
                        f"Error: Zoom level {service_info['zoom']} not available for projection {service_info['proj']}.\n"
                        f"Available zoom levels: {', '.join(available_zooms)}.\n"
                        f"Please choose a zoom level from the available options."
                    )
                    raise ValueError(error_message)
            else:
                downloaded_tiles = download_wms_tiles(service_info, layer_geometry, buffer_distance, zoom_folder, update=update_flag, overwrite=overwrite_flag)
                tile_matrix_zoom = None

            if stitch_tiles:
                processed_tiles = process_and_stitch_tiles(service_info, downloaded_tiles, tile_matrix_zoom, zoom_folder, layer)
                all_tiles.extend(processed_tiles)
            else:
                all_tiles.extend(downloaded_tiles)
        else:
            log_warning(f"Layer {layer} not found for WMTS/WMS download of {layer_name}")

    all_layers[layer_name] = all_tiles
    log_info(f"Total tiles for {layer_name}: {len(all_tiles)}")

    return all_layers[layer_name]

