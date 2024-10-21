import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection, Point, MultiPoint
from src.utils import log_info, log_warning, log_error
from src.operations.common_operations import _process_layer_info, _get_filtered_geometry, ensure_geodataframe
from src.operations.common_operations import *

def create_copy_layer(all_layers, project_settings, crs, layer_name, operation):
    source_layers = operation.get('layers', [])
    combined_geometry = None

    for layer_info in source_layers:
        source_layer_name, values = _process_layer_info(all_layers, project_settings, crs, layer_info)
        if source_layer_name is None:
            continue

        layer_geometry = _get_filtered_geometry(all_layers, project_settings, crs, source_layer_name, values)
        if layer_geometry is None:
            continue

        if combined_geometry is None:
            combined_geometry = layer_geometry
        else:
            combined_geometry = combined_geometry.union(layer_geometry)

    if combined_geometry is not None:
        gdf = gpd.GeoDataFrame(geometry=[combined_geometry], crs=crs)
        all_layers[layer_name] = ensure_geodataframe(all_layers, project_settings, crs, layer_name, gdf)
        log_info(f"Copied layer(s) to {layer_name}")
    else:
        log_warning(f"No valid source layers found for copy operation on {layer_name}")

    return all_layers[layer_name] if layer_name in all_layers else None
