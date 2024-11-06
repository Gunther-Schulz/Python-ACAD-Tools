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
    
    # Get update flag from operation first, then layer_info as fallback
    update_flag = operation.get('update', None)
    if update_flag is None:
        # Check in both geomLayers and wmts_wms_layers
        layer_info = (
            # next((l for l in project_settings.get('geomLayers', []) if l['name'] == layer_name), None) or
            next((l for l in project_settings.get('wmtsLayers', []) if l['name'] == layer_name), None) or
            next((l for l in project_settings.get('wmsLayers', []) if l['name'] == layer_name), None)
        )
        update_flag = layer_info.get('update', False) if layer_info else False
    
    overwrite_flag = operation.get('overwrite', False)
    
    os.makedirs(zoom_folder, exist_ok=True)
    
    log_info(f"Target folder path: {zoom_folder}")
    log_info(f"Update flag: {update_flag}, Overwrite flag: {overwrite_flag}")

    layers = operation.get('layers', [])
    buffer_distance = operation.get('buffer', 100)
    
    # Base service info configuration
    service_info = {
        'url': operation['url'],
        'layer': operation['layer'],
        'proj': operation.get('proj'),
        'srs': operation.get('wmsOptions', {}).get('srs', operation.get('srs')),
        'format': operation.get('wmsOptions', {}).get('format', operation.get('format', 'image/png')),
        'sleep': operation.get('sleep', 0),
        'limit': operation.get('limit', 0),
        'postProcess': operation.get('postProcess', {}),
        'overwrite': overwrite_flag,
        'zoom': zoom_level,
        **operation.get('wmsOptions', {})
    }

    stitch_tiles = operation.get('stitchTiles', False)
    service_info['stitchTiles'] = stitch_tiles

    # Initialize WMTS if needed
    tile_matrix_zoom = None
    if 'wmts' in operation['type'].lower():
        wmts = WebMapTileService(service_info['url'])
        tile_matrix = wmts.tilematrixsets[service_info['proj']].tilematrix
        available_zooms = sorted(tile_matrix.keys(), key=int)
        
        # Zoom level validation and selection
        requested_zoom = service_info.get('zoom')
        chosen_zoom = str(requested_zoom) if requested_zoom is not None else available_zooms[-1]
        
        if str(requested_zoom) not in available_zooms:
            error_message = (
                f"Error: Zoom level {requested_zoom} not available for projection {service_info['proj']}.\n"
                f"Available zoom levels: {', '.join(available_zooms)}."
            )
            raise ValueError(error_message)
        
        service_info['zoom'] = chosen_zoom
        tile_matrix_zoom = tile_matrix[chosen_zoom]

    # Process each layer separately
    all_processed_tiles = []
    for layer in layers:
        if layer not in all_layers:
            log_warning(f"Layer {layer} not found for WMTS/WMS download of {layer_name}")
            continue

        log_info(f"Processing layer: {layer}")
        layer_geometry = all_layers[layer]
        if isinstance(layer_geometry, gpd.GeoDataFrame):
            layer_geometry = layer_geometry.geometry.unary_union

        # Create layer-specific folder
        layer_folder = os.path.join(zoom_folder, layer.replace(" ", "_"))
        os.makedirs(layer_folder, exist_ok=True)

        # Update service info for this specific layer
        layer_service_info = service_info.copy()
        layer_service_info['targetFolder'] = layer_folder

        # Download tiles for this layer
        if 'wmts' in operation['type'].lower():
            downloaded_tiles = download_wmts_tiles(
                layer_service_info, 
                layer_geometry, 
                buffer_distance, 
                layer_folder, 
                update=update_flag, 
                overwrite=overwrite_flag
            )
        else:
            downloaded_tiles = download_wms_tiles(
                layer_service_info, 
                layer_geometry, 
                buffer_distance, 
                layer_folder, 
                update=update_flag, 
                overwrite=overwrite_flag
            )

        # Process tiles for this layer
        if stitch_tiles and downloaded_tiles:
            processed_tiles = process_and_stitch_tiles(
                layer_service_info, 
                downloaded_tiles, 
                tile_matrix_zoom, 
                layer_folder, 
                f"{layer_name}_{layer}"
            )
            all_processed_tiles.extend(processed_tiles)
        else:
            all_processed_tiles.extend(downloaded_tiles)

    all_layers[layer_name] = all_processed_tiles
    log_info(f"Total processed tiles for {layer_name}: {len(all_processed_tiles)}")

    return all_layers[layer_name]